# Project: Coloring Book Generator

This project generates a print-ready A4 coloring book (DOCX) from image URLs.

## Quick Start

The easiest way to generate a coloring book is to use the `create-coloring-book` skill. Tell Claude: "Create a coloring book". The skill will:

1. **Attempt automatic fetch** from Chrome (requires Chrome with `--remote-debugging-port=9222`)
2. If auto-fetch fails, **paste your image URLs** when prompted
3. Overwrite `links.txt` with the URLs
4. Run the script to generate `Kawaii_Coloring_Book_Final.docx`

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

- The `get_chrome_urls.py` script fetches URLs from open Chrome tabs via DevTools Protocol
- To use: launch Chrome with `google-chrome --remote-debugging-port=9222` or adjust for your platform
- The script activates Chrome before fetching. If multiple windows are open, tabs from all windows may be included. Close extra windows for best results.

## Files

- `script.py` - Main script
- `links.txt` - Input: image URLs (always overwritten by skill)
- `Kawaii_Coloring_Book_Final.docx` - Output (generated)
