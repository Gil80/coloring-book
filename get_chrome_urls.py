#!/usr/bin/env python3
"""
Extract the largest image URL from each open Chrome tab via Chrome DevTools Protocol.

Connects to Chrome's CDP endpoint, then for each tab opens a WebSocket to
execute JavaScript that finds all <img> elements and returns the one with the
largest natural dimensions. This mimics "Copy Image Address" for the main image
on each tab.

Requires:
  - Chrome running with --remote-debugging-port=9222
  - pip install websocket-client requests
"""

import os
import sys
import json
import time
import subprocess
import requests

try:
    import websocket
except ImportError:
    print("Error: websocket-client not installed. Run: pip install websocket-client",
          file=sys.stderr)
    sys.exit(1)

# Ports to scan for Chrome DevTools Protocol instances
CHROME_DEBUG_PORTS = [9222, 9223, 9224, 9225]
WS_TIMEOUT = 5


def _get_chrome_hosts():
    """Return list of hostnames to try for Chrome CDP connections.

    On WSL2, localhost may not reach the Windows host, so we also try
    the default gateway IP (which points to the Windows side).
    """
    hosts = ['localhost']
    try:
        with open('/proc/version', 'r') as f:
            if 'microsoft' not in f.read().lower():
                return hosts
    except Exception:
        return hosts
    # WSL2: get the Windows host IP from the default route
    try:
        out = subprocess.check_output(
            ['ip', 'route', 'show', 'default'], text=True)
        for part in out.split():
            if part.count('.') == 3:  # looks like an IP
                if part not in hosts:
                    hosts.append(part)
                break
    except Exception:
        pass
    return hosts


# ---------------------------------------------------------------------------
# Chrome activation
# ---------------------------------------------------------------------------

def activate_chrome():
    """Best-effort: bring Chrome to the foreground."""
    try:
        # Detect WSL
        is_wsl = False
        try:
            with open('/proc/version', 'r') as f:
                is_wsl = 'microsoft' in f.read().lower()
        except Exception:
            pass

        if sys.platform == 'darwin':
            subprocess.run(
                ['osascript', '-e',
                 'tell application "Google Chrome" to activate'],
                check=False)
        elif sys.platform.startswith('win') or is_wsl:
            subprocess.run(
                ['powershell.exe', '-Command',
                 "(New-Object -ComObject WScript.Shell).AppActivate('Google Chrome')"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False)
        else:
            if subprocess.run(['which', 'xdotool'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                subprocess.run(
                    ['xdotool', 'search', '--name',
                     'Google Chrome', 'windowactivate'],
                    check=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Chrome instance discovery
# ---------------------------------------------------------------------------

def discover_chrome_instances():
    """Return a list of Chrome CDP instances reachable on known ports."""
    instances = []
    hosts = _get_chrome_hosts()
    for port in CHROME_DEBUG_PORTS:
        for host in hosts:
            try:
                resp = requests.get(
                    f'http://{host}:{port}/json/version', timeout=2)
                resp.raise_for_status()
                info = resp.json()
                instances.append({
                    'port': port,
                    'host': host,
                    'browser': info.get('Browser', 'Unknown'),
                })
                break  # found on this port, skip remaining hosts
            except Exception:
                continue
    return instances


def fetch_tabs(port, host='localhost'):
    """Get page tabs from the Chrome instance on *host*:*port*."""
    try:
        resp = requests.get(f'http://{host}:{port}/json/list', timeout=2)
        resp.raise_for_status()
        targets = resp.json()
        tabs = []
        for t in targets:
            if t.get('type') == 'page':
                url = t.get('url', '')
                if url.startswith(('http', 'file')):
                    ws_url = t.get('webSocketDebuggerUrl', '')
                    # Chrome reports ws://localhost but we may be connecting
                    # via a different host (e.g. WSL2 gateway IP)
                    if host != 'localhost' and ws_url:
                        ws_url = ws_url.replace('ws://localhost:',
                                                f'ws://{host}:')
                    tabs.append({
                        'url': url,
                        'title': t.get('title', ''),
                        'ws_url': ws_url,
                    })
        return tabs
    except Exception as e:
        print(f"Error fetching tabs from {host}:{port}: {e}",
              file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Per-tab image extraction
# ---------------------------------------------------------------------------

# JavaScript executed inside every tab. Returns a JSON array of image metadata.
_JS_FIND_IMAGES = r"""
(() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    const data = imgs
        .filter(i => i.src && i.src.startsWith('http'))
        .map(i => ({
            src: i.currentSrc || i.src,
            natW: i.naturalWidth  || 0,
            natH: i.naturalHeight || 0,
            natArea: (i.naturalWidth || 0) * (i.naturalHeight || 0),
            dispW: i.offsetWidth  || i.clientWidth  || 0,
            dispH: i.offsetHeight || i.clientHeight || 0,
            dispArea: (i.offsetWidth || i.clientWidth || 0)
                    * (i.offsetHeight || i.clientHeight || 0),
        }));
    return JSON.stringify(data);
})()
"""


def _cdp_evaluate(ws_url, expression):
    """Open a WebSocket to a tab, evaluate *expression*, return the string result."""
    ws = websocket.create_connection(ws_url, timeout=WS_TIMEOUT)
    try:
        ws.send(json.dumps({
            'id': 1,
            'method': 'Runtime.evaluate',
            'params': {'expression': expression, 'returnByValue': True},
        }))
        # Read until we get our response (id == 1)
        deadline = time.monotonic() + WS_TIMEOUT
        while time.monotonic() < deadline:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get('id') == 1:
                return msg.get('result', {}).get('result', {}).get('value')
        return None
    finally:
        ws.close()


def get_largest_image_url(tab):
    """Return the URL of the largest image found in *tab*, or None."""
    ws_url = tab.get('ws_url')
    if not ws_url:
        return None

    try:
        raw = _cdp_evaluate(ws_url, _JS_FIND_IMAGES)
    except Exception as e:
        print(f"  WebSocket error for '{tab['title'][:50]}': {e}",
              file=sys.stderr)
        return None

    if not raw:
        return None

    try:
        images = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not images:
        return None

    # Filter out tiny images (icons, trackers) — keep those > 100 px on a side
    MIN_DIM = 100
    big = [i for i in images
           if i['natW'] > MIN_DIM and i['natH'] > MIN_DIM]
    if not big:
        # Relax: accept anything with a natural area > 0
        big = [i for i in images if i['natArea'] > 0]
    if not big:
        # Last resort: use display dimensions
        big = [i for i in images if i['dispArea'] > 0]
    if not big:
        return None

    # Pick the largest by natural area, tie-break by display area
    big.sort(key=lambda i: (i['natArea'], i['dispArea']), reverse=True)
    return big[0]['src']


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def extract_image_urls(port, host='localhost'):
    """Return a list of image URLs (one per tab) from the Chrome instance on *host*:*port*."""
    tabs = fetch_tabs(port, host)
    if not tabs:
        return []

    urls = []
    for tab in tabs:
        title = tab['title'][:60] or tab['url'][:60]
        print(f"Inspecting: {title}", file=sys.stderr)

        img = get_largest_image_url(tab)
        if img:
            urls.append(img)
            print(f"  -> {img[:120]}", file=sys.stderr)
        else:
            print(f"  -> (no image found)", file=sys.stderr)
    return urls


def _is_wsl():
    """Return True if running inside WSL."""
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except Exception:
        return False


def _try_powershell_extraction():
    """WSL2 fallback: run chrome_extract.ps1 on the Windows side.

    Returns a list of image URLs, or None if the fallback is unavailable.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ps_script = os.path.join(script_dir, 'chrome_extract.ps1')
    if not os.path.exists(ps_script):
        return None

    # Convert WSL path to Windows path for PowerShell
    try:
        win_path = subprocess.check_output(
            ['wslpath', '-w', ps_script], text=True).strip()
    except Exception:
        return None

    print("Direct connection failed; trying PowerShell fallback...",
          file=sys.stderr)

    try:
        result = subprocess.run(
            ['powershell.exe', '-ExecutionPolicy', 'Bypass',
             '-File', win_path],
            capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"PowerShell fallback error: {e}", file=sys.stderr)
        return None

    # Forward stderr (status messages) to our stderr
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            print(line, file=sys.stderr)

    if result.returncode != 0:
        return None

    urls = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
    return urls if urls else None


def main():
    activate_chrome()
    time.sleep(0.5)

    instances = discover_chrome_instances()

    if not instances and _is_wsl():
        # WSL2: direct connection failed, delegate to PowerShell
        urls = _try_powershell_extraction()
        if urls:
            for url in urls:
                print(url)
            sys.exit(0)

    if not instances:
        print("No Chrome DevTools instances found.", file=sys.stderr)
        print("Launch Chrome with: google-chrome --remote-debugging-port=9222",
              file=sys.stderr)
        sys.exit(1)

    # --- Handle multiple instances ---
    if len(instances) > 1:
        print(f"MULTIPLE_INSTANCES_FOUND", file=sys.stderr)
        for inst in instances:
            print(f"  Port {inst['port']} ({inst['host']}): {inst['browser']}",
                  file=sys.stderr)
        # Use the first (lowest port) by default
        port = instances[0]['port']
        host = instances[0]['host']
        print(f"Defaulting to port {port}. "
              "Focus the correct Chrome window and retry if wrong.",
              file=sys.stderr)
    else:
        port = instances[0]['port']
        host = instances[0]['host']
        print(f"Chrome found on {host}:{port} ({instances[0]['browser']})",
              file=sys.stderr)

    image_urls = extract_image_urls(port, host)

    if not image_urls:
        print("No images found in any open tab.", file=sys.stderr)
        sys.exit(2)

    # Print image URLs to stdout, one per line
    for url in image_urls:
        print(url)


if __name__ == '__main__':
    main()
