#!/usr/bin/env python3
"""
Coloring book agent powered by a free LLM via OpenRouter.

Reads the project's Python scripts, understands the workflow, and orchestrates
coloring book creation -- all without requiring Claude Code skills.

Usage:
    python create-book.py              # LLM-assisted mode
    python create-book.py --no-llm     # Direct execution (skip LLM calls)
    python create-book.py --links-only # Only extract URLs, don't generate DOCX

Environment variables (set in .env or export):
    ANTHROPIC_BASE_URL    OpenRouter API base URL
    ANTHROPIC_AUTH_TOKEN  OpenRouter API key
    ANTHROPIC_MODEL       Model ID (default: nvidia/nemotron-3-super-120b-a12b:free)
"""

import os
import sys
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Auto-activate virtualenv if not already active
# ---------------------------------------------------------------------------
_venv_dir = PROJECT_DIR / "venv"
_venv_python = _venv_dir / "bin" / "python"
if _venv_dir.exists() and _venv_python.exists():
    if sys.prefix == sys.base_prefix:  # not inside a venv
        os.environ["VIRTUAL_ENV"] = str(_venv_dir)
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

import json

# ---------------------------------------------------------------------------
# Environment & configuration
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file. Uses python-dotenv if available, otherwise manual parse."""
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # Manual fallback: parse KEY=VALUE lines
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


load_env()

API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://openrouter.ai/api")
MODEL = os.environ.get("ANTHROPIC_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

# OpenRouter uses the OpenAI-compatible /v1 endpoint
if BASE_URL and not BASE_URL.rstrip("/").endswith("/v1"):
    BASE_URL = BASE_URL.rstrip("/") + "/v1"


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

def get_llm_client():
    """Return an OpenAI-compatible client pointed at OpenRouter, or None."""
    if not API_KEY:
        print("[info] No API key found. Running in direct-execution mode.")
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url=BASE_URL, api_key=API_KEY)
    except ImportError:
        print("[info] 'openai' package not installed. Running without LLM.")
        print("       Install with: pip install openai")
        return None


def ask_llm(client, messages):
    """Send messages to the LLM. Returns response text or None on failure."""
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[llm error] {e}")
        return None


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def read_project_file(name):
    """Read a file from the project directory."""
    path = PROJECT_DIR / name
    return path.read_text() if path.exists() else None


def run_cmd(cmd):
    """Run a shell command in the project dir. Returns (rc, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=str(PROJECT_DIR), executable="/bin/bash",
    )
    return result.returncode, result.stdout, result.stderr


def venv_prefix():
    """Shell prefix to activate the virtualenv."""
    venv = PROJECT_DIR / "venv"
    if venv.exists():
        return f"source {venv}/bin/activate && "
    return ""


# ---------------------------------------------------------------------------
# Workflow steps
# ---------------------------------------------------------------------------

def step_extract_urls():
    """Run get_chrome_urls.py and return (list_of_urls, stderr)."""
    print("\n[step 1/3] Extracting image URLs from Chrome tabs...")
    rc, stdout, stderr = run_cmd(f"{venv_prefix()}python get_chrome_urls.py")

    if "MULTIPLE_INSTANCES_FOUND" in stderr:
        print("[warning] Multiple Chrome debug instances detected:")
        for line in stderr.splitlines():
            if line.strip():
                print(f"  {line.strip()}")

    if rc != 0:
        return None, stderr

    # Deduplicate while preserving order
    seen = set()
    urls = []
    for l in stdout.strip().splitlines():
        u = l.strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    return urls, stderr


def step_write_links(urls):
    """Write image URLs to links.txt."""
    print(f"\n[step 2/3] Writing {len(urls)} URL(s) to links.txt...")
    (PROJECT_DIR / "links.txt").write_text("\n".join(urls) + "\n")
    print("  links.txt updated.")


def step_generate_docx():
    """Run script.py to produce the coloring book. Returns (success, stderr)."""
    print("\n[step 3/3] Generating coloring book DOCX...")
    rc, stdout, stderr = run_cmd(f"{venv_prefix()}python script.py")

    if stdout.strip():
        for line in stdout.strip().splitlines():
            print(f"  {line}")

    if rc != 0:
        return False, stderr

    return (PROJECT_DIR / "Kawaii_Coloring_Book_Final.docx").exists(), stderr


# ---------------------------------------------------------------------------
# LLM-assisted helpers
# ---------------------------------------------------------------------------

def build_system_prompt():
    """Build the system message with embedded script contents."""
    script_py = read_project_file("script.py") or "(not found)"
    chrome_py = read_project_file("get_chrome_urls.py") or "(not found)"

    return (
        "You are a coloring book creation assistant. "
        "You understand the following project scripts and help orchestrate their execution.\n\n"
        f"## script.py  (generates A4 DOCX from links.txt)\n```python\n{script_py}\n```\n\n"
        f"## get_chrome_urls.py  (extracts largest image URL per Chrome tab)\n```python\n{chrome_py}\n```\n\n"
        "The workflow is:\n"
        "1. Run get_chrome_urls.py to get image URLs from open Chrome tabs\n"
        "2. Write the URLs to links.txt (one per line)\n"
        "3. Run script.py to generate Kawaii_Coloring_Book_Final.docx\n\n"
        "Be concise and helpful. When troubleshooting, give specific actionable advice."
    )


def llm_plan(client):
    """Ask the LLM to confirm the plan before execution."""
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": (
            "I want to create a coloring book from images open in my Chrome tabs. "
            "Briefly confirm the steps you will take."
        )},
    ]
    plan = ask_llm(client, messages)
    if plan:
        print(f"\n[llm] {plan}\n")
    return messages


def llm_troubleshoot(client, messages, error_context):
    """Ask the LLM for troubleshooting advice."""
    messages.append({
        "role": "user",
        "content": f"Something went wrong:\n{error_context}\nHow do I fix this?",
    })
    advice = ask_llm(client, messages)
    if advice:
        print(f"\n[llm] {advice}")


def llm_summarize(client, messages, url_count):
    """Ask the LLM for a completion summary."""
    messages.append({
        "role": "user",
        "content": f"The coloring book was created successfully with {url_count} images. Brief summary?",
    })
    summary = ask_llm(client, messages)
    if summary:
        print(f"\n[llm] {summary}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    no_llm = "--no-llm" in args
    links_only = "--links-only" in args

    print("=== Coloring Book Agent ===")
    print(f"Model: {MODEL}")

    # LLM setup
    client = None if no_llm else get_llm_client()
    messages = []

    if client:
        print("[llm] Analyzing project scripts and planning...")
        messages = llm_plan(client)
    else:
        print("[mode] Direct execution (no LLM)")

    # --- Step 1: Extract URLs ---
    urls, stderr = step_extract_urls()

    if not urls:
        print("\nFailed to extract image URLs from Chrome.")
        if stderr:
            print(f"Error output:\n{stderr.strip()}")
        if client and messages:
            llm_troubleshoot(client, messages, stderr or "No URLs returned")
        else:
            print("\nTroubleshooting tips:")
            print("  - Is Chrome running with --remote-debugging-port=9222 ?")
            print("  - Are there tabs open with images?")
            print("  - On WSL, Chrome must be on the Windows side.")
        sys.exit(1)

    print(f"\nFound {len(urls)} image(s):")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url[:120]}")

    # --- Step 2: Write links.txt ---
    step_write_links(urls)

    if links_only:
        print("\n--links-only: stopping after links.txt creation.")
        sys.exit(0)

    # --- Step 3: Generate DOCX ---
    success, stderr = step_generate_docx()

    if success:
        print(f"\nColoring book created: Kawaii_Coloring_Book_Final.docx")
        if client and messages:
            llm_summarize(client, messages, len(urls))
    else:
        print("\nFailed to generate coloring book DOCX.")
        if stderr:
            print(f"Error output:\n{stderr.strip()}")
        if client and messages:
            llm_troubleshoot(client, messages, stderr or "script.py failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
