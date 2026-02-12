"""Test PyMuPDF (fitz) extraction against the sample Electric Ireland bill."""
import pymupdf

PDF_PATH = "/Users/donalocallaghan/workspace/vibes/steve/download.pdf"

doc = pymupdf.open(PDF_PATH)
print(f"Total pages: {doc.page_count}")
print(f"Metadata: {doc.metadata}")
print()

for i, page in enumerate(doc):
    print(f"{'='*60}")
    print(f"PAGE {i+1} (size: {page.rect.width}x{page.rect.height})")
    print(f"{'='*60}")

    # Extract text - standard
    text = page.get_text()
    if text.strip():
        print(f"\n--- TEXT (get_text(), length={len(text.strip())}) ---")
        print(text.strip())
    else:
        print("\n--- NO TEXT via get_text() ---")

    # Extract text - blocks mode for structured extraction
    blocks = page.get_text("blocks")
    text_blocks = [b for b in blocks if b[6] == 0]  # type 0 = text
    image_blocks = [b for b in blocks if b[6] == 1]  # type 1 = image

    if text_blocks:
        print(f"\n--- TEXT BLOCKS ({len(text_blocks)} blocks) ---")
        for b in text_blocks:
            x0, y0, x1, y1, text_content, block_no, block_type = b
            text_content = text_content.strip()
            if text_content:
                print(f"  [{x0:.0f},{y0:.0f} -> {x1:.0f},{y1:.0f}] {text_content[:100]}")

    if image_blocks:
        print(f"\n--- IMAGE BLOCKS ({len(image_blocks)} found) ---")
        for b in image_blocks:
            x0, y0, x1, y1 = b[:4]
            print(f"  Image at [{x0:.0f},{y0:.0f} -> {x1:.0f},{y1:.0f}], size: {x1-x0:.0f}x{y1-y0:.0f}")

    # Try dict mode for word-level extraction
    text_dict = page.get_text("dict")
    word_count = sum(
        len(span["text"].strip()) > 0
        for block in text_dict["blocks"]
        if block["type"] == 0
        for line in block["lines"]
        for span in line["spans"]
    )
    print(f"\n  Total text spans on page: {word_count}")

    print()

doc.close()
