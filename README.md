# Coloring Book Generator

A Python script that downloads images from a list of URLs and assembles them into a print-ready A4 coloring book (DOCX format), with two images per page.

## How It Works

1. Reads image URLs from `links.txt` (one URL per line)
2. Downloads each image and embeds it into a Word document
3. Lays out two images per A4 page with minimal margins
4. Outputs `Kawaii_Coloring_Book_Final.docx`

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Add image URLs to `links.txt`, one per line
2. Run the script:

```bash
python script.py
```

The generated DOCX file will appear in the project directory.

## Dependencies

- [python-docx](https://python-docx.readthedocs.io/) - Word document generation
- [Requests](https://docs.python-requests.org/) - Image downloading
- [Pillow](https://pillow.readthedocs.io/) - Image processing
