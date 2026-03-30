#!/usr/bin/env python3
"""
Fetch image URLs from open Chrome tabs using Chrome DevTools Protocol.
Requires Chrome to be running with remote debugging enabled on port 9222.
"""

import sys
import time
import subprocess
import requests

def activate_chrome():
    """Attempt to bring Chrome to the foreground."""
    platform = sys.platform
    try:
        if platform == 'darwin':
            subprocess.run(['osascript', '-e', 'tell application "Google Chrome" to activate'], check=False)
        elif platform.startswith('win'):
            # In WSL, call PowerShell to activate Chrome window on Windows
            subprocess.run(['powershell.exe', '-Command',
                           "(New-Object -ComObject WScript.Shell).AppActivate('Google Chrome')"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            # Linux: try xdotool if available
            if subprocess.run(['which', 'xdotool'], stdout=subprocess.DEVNULL).returncode == 0:
                subprocess.run(['xdotool', 'search', '--name', 'Google Chrome', 'windowactivate'], check=False)
    except Exception:
        pass  # Activation is best-effort

def fetch_tabs_via_cdp():
    """Connect to Chrome DevTools Protocol and fetch tab URLs."""
    try:
        resp = requests.get('http://localhost:9222/json/list', timeout=2)
        resp.raise_for_status()
        targets = resp.json()
        urls = []
        for t in targets:
            if t.get('type') == 'page':
                url = t.get('url', '')
                # Include only http/https/file URLs; skip internal chrome:// pages
                if url.startswith('http') or url.startswith('file'):
                    urls.append(url)
        return urls
    except Exception as e:
        print(f"Error connecting to Chrome DevTools Protocol: {e}", file=sys.stderr)
        return None

if __name__ == '__main__':
    activate_chrome()
    time.sleep(0.5)  # brief pause after activation
    urls = fetch_tabs_via_cdp()
    if urls is None:
        sys.exit(1)  # connection error
    if not urls:
        print("No page tabs found.", file=sys.stderr)
        sys.exit(2)
    for url in urls:
        print(url)
