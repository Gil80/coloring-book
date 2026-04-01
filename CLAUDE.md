# Project: Coloring Book Generator

This project generates a print-ready A4 coloring book (DOCX) from image URLs.

## Quick Start

The easiest way to generate a coloring book is to use the `create-coloring-book` skill. Tell Claude: "Create a coloring book". The skill will:

1. **Switch to Chrome** and extract the **actual image URLs** (Copy Image Address) from every open tab
2. If a tab has multiple images, the **largest image** is selected automatically
3. If auto-fetch fails or multiple Chrome instances are detected, you'll be prompted
4. Overwrite `links.txt` with the image URLs
5. Run the script to generate `Kawaii_Coloring_Book_Final.docx`

## Agent Mode (OpenRouter Free LLM)

The project includes `create-book.py`, a standalone agent that uses a free LLM via OpenRouter to orchestrate coloring book creation without Claude Code skills. It auto-activates the virtualenv -- no need to `source venv/bin/activate` first.

```bash
python create-book.py              # LLM-assisted mode (reads scripts, plans, executes)
python create-book.py --no-llm     # Direct execution (skip LLM, just run the workflow)
python create-book.py --links-only # Only extract URLs to links.txt, don't generate DOCX
```

Configuration is in `.env` (gitignored):
- `ANTHROPIC_BASE_URL` - OpenRouter API endpoint
- `ANTHROPIC_AUTH_TOKEN` - OpenRouter API key
- `ANTHROPIC_MODEL` - Model ID (default: `nvidia/nemotron-3-super-120b-a12b:free`)

The agent reads `script.py` and `get_chrome_urls.py`, sends them to the LLM for understanding, then executes the 3-step workflow. If the LLM is unavailable, it falls back to direct execution.

## Manual Usage

If running manually:

```bash
source venv/bin/activate
python script.py
```

Ensure `links.txt` exists with one URL per line before running.

## Project Notes

- `links.txt` format: one image URL per line, no commas, no blank lines
- Script outputs two images per A4 page with minimal margins
- Images are downloaded, converted to PNG, and embedded
- Output: `Kawaii_Coloring_Book_Final.docx`
- Any errors during image download or processing are printed to stdout but script continues

## Chrome Integration

- `get_chrome_urls.py` connects to each Chrome tab via CDP WebSocket and executes JavaScript to find all `<img>` elements
- It returns the **image source URL** (equivalent to "Copy Image Address") of the **largest image** per tab
- Tiny images (icons, tracking pixels) are filtered out automatically
- Requires Chrome with `--remote-debugging-port=9222` (scans ports 9222-9225)
- On WSL, the script uses `powershell.exe` to activate Chrome on the Windows side
- If multiple Chrome debugging instances are detected, the script prints `MULTIPLE_INSTANCES_FOUND` to stderr — the skill will prompt the user to confirm which instance
- Dependency: `websocket-client` (for CDP WebSocket connections to individual tabs)

## Files

- `script.py` - Main coloring book generator
- `get_chrome_urls.py` - Extracts largest image URL from each Chrome tab via CDP
- `links.txt` - Input: image URLs (always overwritten by skill)
- `create-book.py` - LLM-powered agent that orchestrates the full workflow via OpenRouter (auto-activates venv)
- `.env` - OpenRouter API configuration (gitignored, not committed)
- `requirements.txt` - Dependencies: `python-docx`, `requests`, `Pillow`, `websocket-client`, `openai`, `python-dotenv`
- `Kawaii_Coloring_Book_Final.docx` - Output (generated)
