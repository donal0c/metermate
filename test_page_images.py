"""
Check what's on pages 2 and 4 (the image-only pages).
Extract images and save them for inspection.
"""
import pymupdf
import os

PDF_PATH = "/Users/donalocallaghan/workspace/vibes/steve/download.pdf"
OUTPUT_DIR = "/Users/donalocallaghan/workspace/vibes/steve/extracted_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

doc = pymupdf.open(PDF_PATH)

for page_num in range(doc.page_count):
    page = doc[page_num]

    # Render page to image for visual inspection
    pix = page.get_pixmap(dpi=150)
    img_path = os.path.join(OUTPUT_DIR, f"page_{page_num+1}.png")
    pix.save(img_path)
    print(f"Page {page_num+1} rendered to {img_path} ({pix.width}x{pix.height})")

    # List embedded images
    image_list = page.get_images(full=True)
    print(f"  Embedded images: {len(image_list)}")
    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        base_image = doc.extract_image(xref)
        img_ext = base_image["ext"]
        img_size = len(base_image["image"])
        print(f"    Image {img_idx}: xref={xref}, format={img_ext}, "
              f"size={img_size} bytes, "
              f"dimensions={base_image.get('width', '?')}x{base_image.get('height', '?')}")

doc.close()
print("\nDone - check extracted_images/ folder")
