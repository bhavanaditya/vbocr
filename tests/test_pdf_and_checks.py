"""Tests for digital PDFs, the total check, unsure values, the item list and the scan history.

No OCR engine needed: python -m pytest tests
"""

import json

from test_extractor import SAMPLE_SUPPLIER, garment_invoice, settings_with, w

from vbocr.extractor import extract_invoice
from vbocr.gstin import check_char
from vbocr.history import History
from vbocr.models import Invoice
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


TEST_GSTIN = "29AAGCS1234K1Z" + check_char("29AAGCS1234K1Z")


def invoice_pdf_lines(grand_total="4741.10"):
    """The garment invoice from test_extractor, as PDF text (coordinates in points)."""
    lines = [
        (130, 40, 10, "TAX INVOICE"),
        (50, 60, 16, "Sample Garments Pvt Ltd"),
        (50, 82, 9, "GSTIN : " + TEST_GSTIN),
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
    assert invoice.supplier_gstin == TEST_GSTIN


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


def test_corrections_are_learned_and_counted(tmp_path):
    from vbocr import item_master

    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    learned_file = tmp_path / "learned.csv"
    settings.data["item_master"] = {"learned_file": str(learned_file), "learn": True}
    history = History(tmp_path / "history")
    invoice = extract_invoice([garment_invoice()], settings)
    history.record(invoice, "csv", ["bill.jpg"])

    corrected = Invoice.from_dict(invoice.to_dict())
    corrected.items[0]["size"] = "XL"          # not printed: typed by the user
    corrected.items[1]["quantity"] = "4"      # OCR misread
    del corrected.items[2]                    # wrong row
    corrected.items.append(dict(corrected.items[0], sku="NEW001", size="M"))
    original = history.update(invoice.scan_id, corrected, "csv2")
    assert original["items"][1]["quantity"] == "1"

    saved = history.get(invoice.scan_id)
    kinds = {(c.get("row"), c.get("field") or c.get("kind")) for c in saved["changes"]}
    assert kinds == {(1, "size"), (2, "quantity"), (3, "row_added"), (3, "row_deleted")}
    stats = history.correction_stats()
    assert stats["scans"] == 1 and stats["corrected"] == 1
    assert stats["fields"] == {"size": 1, "quantity": 1}
    assert stats["suppliers"][0]["name"] == "Sample Garments Pvt Ltd"

    assert item_master.learn(learned_file, "Sample Garments Pvt Ltd", original["items"], corrected.items) >= 2
    again = extract_invoice([garment_invoice()], settings)
    assert again.items[0]["size"] == "XL"      # filled from what was learned

    # the invoice shows a different M.R.P than the list: marked for checking
    item_master.learn(learned_file, "Sample Garments Pvt Ltd", again.items,
                      [dict(again.items[0], mrp="1099.00")] + again.items[1:])
    third = extract_invoice([garment_invoice()], settings)
    assert third.items[0]["mrp"] == "999.00" and {"row": 1, "field": "mrp"} in third.unsure


def test_total_check_explains_taxes_charges_and_discount(tmp_path):
    from test_extractor import w

    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    settings.data["checks"].update({
        "tax_labels": ["cgst", "sgst", "igst"], "charge_labels": ["freight", "round off"],
        "discount_labels": ["discount"]})
    page = garment_invoice()  # items 4741.10; prints Grand Total 5743.10 -> change it
    for word in page.words:
        if word.text == "5743.10":
            word.text = "5060.00"
    # 4741.10 - 100.00 + 2.5% CGST/SGST of 4641.10 (116.03 each) + 186.80 freight + 0.04 round off
    page.words += [
        w("Discount", 600, 600, 700, 618), w("(-)100.00", 990, 600, 1060, 618),
        w("CGST @ 2.5%", 600, 625, 720, 643), w("116.03", 990, 625, 1050, 643),
        w("Add: SGST @2.5 %", 600, 650, 740, 668), w("2.5%", 800, 650, 840, 668), w("116.03", 990, 650, 1050, 668),
        w("Freight", 600, 675, 680, 693), w("186.80", 990, 675, 1050, 693),
        w("Round off", 600, 700, 690, 718), w("0.04", 1000, 700, 1040, 718),
    ]
    check = extract_invoice([page], settings).total_check
    assert check["status"] == "ok", check
    labels = [a["label"] for a in check["adjustments"]]
    assert {"Discount", "CGST", "SGST", "Freight"} <= set(labels)  # round off 0.04 is within tolerance
    assert check["adjustments"][labels.index("Discount")]["value"] == "-100.00"
    assert check["note"].startswith("printed total = items")
