"""Tests for digital PDFs, the total check, unsure values, the item list and the scan history.

No OCR engine needed: python -m pytest tests
"""

import json

from test_extractor import SAMPLE_SUPPLIER, garment_invoice, settings_with, w

from vbocr.extractor import extract_invoice
from vbocr.history import History
from vbocr.pdf import read_pdf


def make_pdf(path, lines, page_height=842):
    """Write a one-page PDF with real text. ``lines`` = [(x, y_from_top, size, text), ...]."""
    stream = "BT\n"
    for x, y, size, text in lines:
        text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream += "/F1 {} Tf 1 0 0 1 {} {} Tm ({}) Tj\n".format(size, x, page_height - y, text)
    stream += "ET\n"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 {}] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>".format(page_height),
        "<< /Length {} >>\nstream\n{}endstream".format(len(stream.encode("latin-1")), stream),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += "{} 0 obj\n{}\nendobj\n".format(number, body).encode("latin-1")
    xref = len(out)
    out += "xref\n0 {}\n0000000000 65535 f \n".format(len(objects) + 1).encode()
    for offset in offsets:
        out += "{:010d} 00000 n \n".format(offset).encode()
    out += "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(len(objects) + 1, xref).encode()
    path.write_bytes(out)


def invoice_pdf_lines(grand_total="4741.10"):
    """The garment invoice from test_extractor, as PDF text (coordinates in points)."""
    lines = [
        (130, 40, 10, "TAX INVOICE"),
        (50, 60, 16, "Sample Garments Pvt Ltd"),
        (30, 110, 9, "Brand : Lumina"),
        (30, 130, 9, "Invoice No. : SG/25-26/0042"),
        (30, 145, 9, "Invoice Date : 05-02-2026"),
        (30, 200, 9, "S.No."), (60, 200, 9, "Item"), (130, 200, 9, "Product"), (200, 200, 9, "HSN"),
        (250, 194, 9, "Total"), (250, 206, 9, "Qty"), (290, 200, 9, "MRP"), (340, 200, 9, "WS Price"),
        (500, 200, 9, "Total"),
    ]
    rows = [("1", "LMN0101BLK", "NIGHTWEAR", "62082100", "2", "999.00", "669.33", "1335.32"),
            ("2", "LMN0102PNK", "NIGHTWEAR", "62082100", "1", "1,199.00", "803.33", "801.32"),
            ("3", "LMN0103XYZ", "DAYWEAR", "62092000", "3", "1299.00", "870.33", "2604.46")]
    for i, (sno, sku, product, hsn, qty, mrp, price, total) in enumerate(rows):
        y = 225 + i * 16
        lines += [(35, y, 9, sno), (60, y, 9, sku), (130, y, 9, product), (200, y, 9, hsn),
                  (258, y, 9, qty), (290, y, 9, mrp), (345, y, 9, price), (500, y, 9, total)]
    lines += [(30, 300, 9, "Grand Total"), (500, 300, 9, grand_total)]
    return lines


def test_pdf_text_layer_is_read_without_ocr(tmp_path):
    path = tmp_path / "bill.pdf"
    make_pdf(path, invoice_pdf_lines())
    parts = read_pdf(str(path))
    assert [kind for kind, _ in parts] == ["text"]
    page = parts[0][1]
    assert page.source == "pdf-text"
    texts = [w.text for w in page.words]
    assert "Invoice No. : SG/25-26/0042" in texts
    assert "LMN0101BLK" in texts and "1,199.00" in texts

    invoice = extract_invoice([page], settings_with(tmp_path, SAMPLE_SUPPLIER))
    assert invoice.header["invoice_number"] == "SG/25-26/0042"
    assert [i["amount"] for i in invoice.items] == ["1335.32", "801.32", "2604.46"]
    assert invoice.items[1]["mrp"] == "1199.00"
    assert invoice.total_check["status"] == "ok"
    assert invoice.unsure == []


def test_pdf_without_text_is_rendered_for_ocr(tmp_path):
    path = tmp_path / "scan.pdf"
    make_pdf(path, [(30, 40, 9, "x")])  # almost no text = a scanned page
    parts = read_pdf(str(path))
    assert parts[0][0] == "image"
    assert parts[0][1].ndim == 3 and parts[0][1].shape[2] == 3


def test_total_check(tmp_path):
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    page = garment_invoice()  # prints Grand Total 5743.10, items add up to 4741.10
    invoice = extract_invoice([page], settings)
    assert invoice.total_check["status"] == "mismatch"
    assert invoice.total_check["printed_total"] == "5743.10"
    assert any(warning.startswith("Total check:") for warning in invoice.warnings)

    for word in page.words:
        if word.text == "5743.10":
            word.text = "4741.10"
    assert extract_invoice([page], settings).total_check["status"] == "ok"

    for word in page.words:
        if word.text == "4741.10":
            word.text = "4978.16"  # 4741.10 + 5% GST
    check = extract_invoice([page], settings).total_check
    assert check["status"] == "ok" and "5% GST" in check["note"]


def test_unsure_values(tmp_path):
    page = garment_invoice()
    for word in page.words:
        if word.text == "801.32":
            word.score = 0.6
        if word.text == "1299.00":
            word.text = "l299.00"  # letter l read instead of 1
    invoice = extract_invoice([page], settings_with(tmp_path, SAMPLE_SUPPLIER))
    assert {"row": 2, "field": "amount"} in invoice.unsure
    assert {"row": 3, "field": "mrp"} in invoice.unsure
    assert invoice.items[2]["mrp"] == "1299.00"


def test_item_master_fills_missing_values(tmp_path):
    (tmp_path / "items.csv").write_text(
        "SKU No./Item ID.,Article ID,Size,M.R.P,Supplier\n"
        "lmn-0101-blk,A-1,M,1000.00,\n"
        "LMN0102PNK,A-2,L,,Other Supplier\n",
        encoding="utf-8",
    )
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    settings.data["item_master"] = {"file": str(tmp_path / "items.csv"), "overwrite": False}
    invoice = extract_invoice([garment_invoice()], settings)
    first, second = invoice.items[0], invoice.items[1]
    assert (first["article_id"], first["size"]) == ("A-1", "M")
    assert first["mrp"] == "999.00"  # printed value kept (overwrite: false)
    assert second["article_id"] == ""  # row belongs to another supplier


def test_history_duplicates_and_corrections(tmp_path):
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    history = History(tmp_path / "history")
    first = extract_invoice([garment_invoice()], settings)
    history.record(first, "csv-1", ["bill.jpg"])
    assert first.scan_id and not first.duplicates

    again = extract_invoice([garment_invoice()], settings)
    history.record(again, "csv-2", ["bill-again.jpg"])
    assert again.duplicates and again.duplicates[0]["id"] == first.scan_id
    assert any(warning.startswith("Already scanned on") for warning in again.warnings)

    recent = history.recent()
    assert [r["id"] for r in recent] == [again.scan_id, first.scan_id]
    assert history.recent(query="sg/25-26/0042") and not history.recent(query="nothing")

    again.items[0]["quantity"] = "5"
    assert history.update(again.scan_id, again, "csv-corrected")
    saved = history.get(again.scan_id)
    assert saved["csv"] == "csv-corrected" and saved["items"][0]["quantity"] == "5" and saved["corrected"]
    assert history.get("../../etc/passwd") is None
    json.dumps(saved)
