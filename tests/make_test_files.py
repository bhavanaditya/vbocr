"""Create test invoices: python tests/make_test_files.py <folder>

    a_bill.jpg            clean invoice image (items add up to 4741.10, prints 5743.10)
    b_bill.png            same, transparent PNG
    c_bad.png             damaged file
    readme.txt            not an invoice
    photo/angled.jpg      phone photo: page at an angle on a table, with a shadow
    photo/upside_down.jpg photo taken upside down
    digital-invoice.pdf   PDF with real text (total matches)
    two-invoices.pdf      two invoices in one PDF

Used by the end-to-end OCR test and the Windows CI. Needs Pillow >= 10.1 and numpy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

from test_pdf_and_checks import invoice_pdf_lines, make_pdf  # noqa: E402

SCALE = 4  # PDF points -> pixels


def render_invoice(grand_total="5743.10", invoice_number="SG/25-26/0042"):
    """The test invoice as a Pillow RGB image (2310 x 1340)."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (2310, 1340), "white")
    draw = ImageDraw.Draw(image)
    fonts = {}
    for x, y, size, text in invoice_pdf_lines(grand_total):
        if size not in fonts:
            fonts[size] = ImageFont.load_default(size=int(size * 2.5))
        draw.text((x * SCALE, y * SCALE), text.replace("SG/25-26/0042", invoice_number),
                  fill="black", font=fonts[size], anchor="ls")
    return image


def photo_at_angle(image):
    """Put the page on a table at an angle, with a shadow, like a quick phone photo."""
    import numpy as np
    from PIL import Image

    try:
        import cv2
    except ImportError:
        return None
    page = np.asarray(image)[:, :, ::-1]
    h, w = page.shape[:2]
    rng = np.random.default_rng(1)
    table = (rng.normal(70, 12, (2400, 3200, 3)) + np.array([20, 45, 80])).clip(0, 255).astype("uint8")
    corners = np.float32([[420, 380], [2850, 250], [2950, 1950], [300, 2150]])
    matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), corners)
    warped = cv2.warpPerspective(page, matrix, (3200, 2400))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), matrix, (3200, 2400))
    photo = np.where(mask[..., None] > 0, warped, table).astype("float32")
    yy, xx = np.mgrid[0:2400, 0:3200]
    shade = np.linspace(0.55, 1.0, 3200)[None, :] * (1 - 0.35 * np.exp(-(((xx - 900) / 600.0) ** 2 + ((yy - 1700) / 450.0) ** 2)))
    photo = (photo * shade[..., None]).clip(0, 255).astype("uint8")
    return Image.fromarray(photo[:, :, ::-1])


def make_all(folder):
    from PIL import Image

    folder = Path(folder)
    (folder / "photo").mkdir(parents=True, exist_ok=True)
    image = render_invoice()
    image.save(folder / "a_bill.jpg", quality=92)
    rgba = image.convert("RGBA")
    rgba.putalpha(Image.eval(image.convert("L"), lambda v: 255 - v))  # only the text is opaque
    rgba.save(folder / "b_bill.png")
    (folder / "c_bad.png").write_bytes(b"this is not an image")
    (folder / "readme.txt").write_text("not an invoice")
    image.rotate(180).save(folder / "photo" / "upside_down.jpg", quality=90)
    photo = photo_at_angle(image)
    if photo is not None:
        photo.save(folder / "photo" / "angled.jpg", quality=85)
    make_pdf(folder / "digital-invoice.pdf", invoice_pdf_lines("4741.10"))
    try:
        import pypdfium2 as pdfium

        make_pdf(folder / "_b.pdf", [(x, y, s, t.replace("0042", "0043")) for x, y, s, t in invoice_pdf_lines("4741.10")])
        both = pdfium.PdfDocument(str(folder / "digital-invoice.pdf"))
        second = pdfium.PdfDocument(str(folder / "_b.pdf"))
        both.import_pages(second)
        both.save(str(folder / "two-invoices.pdf"))
        both.close()
        second.close()
        (folder / "_b.pdf").unlink()
    except ImportError:
        pass


if __name__ == "__main__":
    make_all(sys.argv[1] if len(sys.argv) > 1 else "test-files")
    print("Test files written to", sys.argv[1] if len(sys.argv) > 1 else "test-files")
