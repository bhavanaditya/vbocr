"""Tests for table rebuilding, header fields and CSV output.

The tests use hand-made OCR boxes, so PaddleOCR is not needed to run them:
    python -m pytest tests
"""

import csv
import io

from vbocr.config import Settings
from vbocr.csv_output import invoice_to_csv
from vbocr.extractor import extract_invoice
from vbocr.models import Page, Word


def w(text, x1, y1, x2, y2):
    return Word(text, 0.99, x1, y1, x2, y2)


def garment_invoice(skew=0.0):
    """A small invoice laid out like a typical garment supplier bill.

    ``skew`` moves every box down by ``skew * x`` pixels, like a photo taken at an angle.
    """
    words = [
        w("TAX INVOICE", 260, 30, 370, 50),
        w("Sample Garments Pvt Ltd", 100, 60, 500, 95),
        w("Brand : Lumina", 60, 200, 200, 220),
        w("PO No", 320, 200, 370, 220),
        w(": PO-778", 400, 200, 480, 220),
        w("Invoice No. : SG/25-26/0042", 60, 240, 300, 260),
        w("Invoice Date : 05-02-2026", 60, 265, 260, 285),
        # header, "Total Qty" printed on two lines
        w("S.No.", 60, 400, 100, 420),
        w("Item", 110, 400, 150, 420),
        w("Product", 240, 400, 300, 420),
        w("HSN", 340, 400, 380, 420),
        w("Total", 415, 394, 455, 414),
        w("Qty", 415, 410, 455, 430),
        w("MRP", 470, 400, 510, 420),
        w("WS Price", 530, 400, 600, 420),
        w("Total", 990, 400, 1040, 420),
    ]
    rows = [
        ("1", "LMN0101BLK", "NIGHTWEAR", "62082100", "2", "999.00", "669.33", "1335.32"),
        ("2", "LMN0102PNK", "NIGHTWEAR", "62082100", "1", "1,199.00", "803.33", "801.32"),
        ("3", "LMN0103XYZ", None, None, "3", "1299.00", "870.33", "2604.46"),
    ]
    for i, (sno, sku, product, hsn, qty, mrp, price, total) in enumerate(rows):
        y = 440 + i * 24
        words += [w(sno, 70, y, 85, y + 18), w(sku, 100, y, 235, y + 18)]
        if product:
            words += [w(product, 240, y, 340, y + 18), w(hsn, 342, y, 412, y + 18)]
        else:
            # OCR merged two neighbouring cells into one box
            words.append(w("DAYWEAR62092000", 238, y, 410, y + 18))
        words += [
            w(qty, 440, y, 455, y + 18),
            w(mrp, 465, y, 520, y + 18),
            w(price, 560, y, 615, y + 18),
            w(total, 990, y, 1055, y + 18),
        ]
    words.append(w("Grand Total", 60, 600, 200, 620))
    words.append(w("5743.10", 990, 600, 1055, 620))
    if skew:
        words = [Word(x.text, x.score, x.x1, x.y1 + skew * x.x1, x.x2, x.y2 + skew * x.x1) for x in words]
    return Page(words=words, width=1100, height=1400)


def fabric_invoice():
    words = [
        w("Ref No", 220, 200, 290, 220),
        w(":ST 900", 360, 200, 440, 220),
        w("Ref Date", 220, 230, 300, 250),
        w(":30/01/2026", 360, 230, 480, 250),
        w("LR No. & Date", 740, 230, 850, 250),
        w(":", 900, 230, 910, 250),
        w("S.NO", 208, 470, 246, 490),
        w("Description of Goods", 416, 474, 559, 491),
        w("HSN Code", 743, 476, 812, 493),
        w("PCS", 940, 478, 969, 494),
        w("Mtrs", 1004, 477, 1042, 496),
        w("Rate", 1094, 479, 1132, 497),
        w("Total Amt", 1182, 478, 1256, 498),
        w("1", 207, 521, 223, 541),
        w("ACME/CLASSIC TWILL/7001", 247, 521, 510, 544),
        w("520843", 728, 525, 792, 546),
        w("1", 968, 529, 981, 547),
        w("13.60", 1013, 529, 1062, 548),
        w("675.00", 1103, 530, 1165, 551),
        w("9180.00", 1201, 531, 1274, 552),
    ]
    return Page(words=words, width=1400, height=900)


def settings_with(tmp_path, suppliers_yaml=""):
    from vbocr.config import DEFAULT_CONFIG_DIR

    (tmp_path / "settings.yaml").write_text((DEFAULT_CONFIG_DIR / "settings.yaml").read_text())
    (tmp_path / "suppliers.yaml").write_text(suppliers_yaml or "suppliers: []\n")
    return Settings(tmp_path)


SAMPLE_SUPPLIER = """
suppliers:
  - name: Sample Garments Pvt Ltd
    match: ["sample garments"]
    colour_from_sku_suffix: 3
"""


def test_garment_invoice_header_and_items(tmp_path):
    invoice = extract_invoice([garment_invoice()], settings_with(tmp_path, SAMPLE_SUPPLIER))

    assert invoice.header["supplier_name"] == "Sample Garments Pvt Ltd"
    assert invoice.header["invoice_number"] == "SG/25-26/0042"
    assert invoice.header["invoice_date"] == "05-02-2026"
    assert invoice.header["po_number"] == "PO-778"
    assert len(invoice.items) == 3

    first = invoice.items[0]
    assert first["sku"] == "LMN0101BLK"
    assert first["design_name"] == "NIGHTWEAR"
    assert first["brand"] == "Lumina"
    assert first["colour"] == "Black"
    assert first["quantity"] == "2"
    assert first["cost_price"] == "669.33"
    assert first["mrp"] == "999.00"
    assert first["amount"] == "1335.32"
    assert invoice.items[1]["mrp"] == "1199.00"  # thousands separator removed


def test_merged_cells_are_split(tmp_path):
    invoice = extract_invoice([garment_invoice()], settings_with(tmp_path, SAMPLE_SUPPLIER))
    assert invoice.items[2]["design_name"] == "DAYWEAR"
    assert invoice.items[2]["colour"] == "XYZ"  # unknown code is kept as printed


def test_skewed_photo(tmp_path):
    invoice = extract_invoice([garment_invoice(skew=0.02)], settings_with(tmp_path, SAMPLE_SUPPLIER))
    assert [i["amount"] for i in invoice.items] == ["1335.32", "801.32", "2604.46"]
    assert [i["quantity"] for i in invoice.items] == ["2", "1", "3"]


def test_unknown_supplier_still_reads_table(tmp_path):
    invoice = extract_invoice([garment_invoice()], settings_with(tmp_path))
    assert invoice.header["supplier_name"] == "Sample Garments Pvt Ltd"
    assert len(invoice.items) == 3
    assert invoice.items[0]["colour"] == ""


def test_fabric_invoice_description_pattern(tmp_path):
    invoice = extract_invoice([fabric_invoice()], settings_with(tmp_path))
    assert invoice.header["invoice_number"] == "ST 900"
    assert invoice.header["invoice_date"] == "30-01-2026"
    assert invoice.header["lr_booking_date"] == ""
    item = invoice.items[0]
    assert (item["brand"], item["design_name"], item["article_id"]) == ("ACME", "CLASSIC TWILL", "7001")
    assert item["quantity"] == "13.60"  # metres preferred over pieces
    assert item["cost_price"] == "675.00"
    assert item["amount"] == "9180.00"


def test_csv_layout(tmp_path):
    invoice = extract_invoice([garment_invoice()], settings_with(tmp_path, SAMPLE_SUPPLIER))
    rows = list(csv.reader(io.StringIO(invoice_to_csv(invoice))))

    assert rows[0][:3] == ["", "Date", "Supplier Name"]
    assert rows[1][2] == "Sample Garments Pvt Ltd"
    assert rows[2] == []
    assert rows[3][0] == "Sl.No" and rows[3][-1] == "Amount"
    assert rows[4][:2] == ["1", "LMN0101BLK"]
    assert rows[-1][0] == "Total"
    assert rows[-1][8] == "6"
    assert rows[-1][11] == "4741.10"
    assert all(len(r) == 12 for r in rows[3:])
