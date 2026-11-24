# pdf_reader.py
# Reads a PDF and returns its text one page at a time,
# so every piece of text can be traced back to a page number (needed for citations).

import fitz     # Using PyMuPDF


def extract_pages(pdf_path):
    pages = []
    doc = fitz.open(pdf_path)

    for i, page in enumerate(doc):
        text = page.get_text()

        # Add 1 to the index to get real page numbers
        pages.append({"page": i + 1, "text": text})

    doc.close()
    return pages