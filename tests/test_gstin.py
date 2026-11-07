"""GSTIN reading: check character, look-alike repairs, supplier vs buyer, duplicates."""

from test_extractor import SAMPLE_SUPPLIER, garment_invoice, settings_with, w

from vbocr import gstin
from vbocr.extractor import extract_invoice
from vbocr.history import History


def _valid(first14):
    return first14 + gstin.check_char(first14)


SUPPLIER = _valid("29AAGCS1234K1Z")
BUYER = _valid("29BBBPK5678L1Z")


def test_check_character():
    assert gstin.is_valid("27AAPFU0939F1ZV")          # published example
    assert not gstin.is_valid("27AAPFU0939F1ZW")
    assert gstin.is_valid(SUPPLIER) and gstin.is_valid(BUYER)


def test_repairs_look_alike_characters():
    misread = "2" + "9" + "AAGC5" + "I234" + "K1Z" + SUPPLIER[14]   # S read as 5, 1 read as I
    assert gstin.repair(misread) == (SUPPLIER, True)
    assert gstin.repair(SUPPLIER[:14] + ("A" if SUPPLIER[14] != "A" else "B")) == (
        SUPPLIER[:14] + ("A" if SUPPLIER[14] != "A" else "B"), False)
    assert gstin.repair("hello") == ("HELLO", False)


def _invoice_page(supplier_text="GSTIN : " + SUPPLIER):
    page = garment_invoice()
    page.words += [w(supplier_text, 100, 100, 400, 118),
                   w("Bill To:", 600, 170, 680, 188), w("GSTIN: " + BUYER, 600, 192, 900, 210)]
    return page


def test_supplier_gstin_not_the_buyer(tmp_path):
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    invoice = extract_invoice([_invoice_page()], settings)
    assert invoice.supplier_gstin == SUPPLIER
    # buyer GSTIN printed first: still not taken, because it is under "Bill To"
    page = garment_invoice()
    page.words += [w("Bill To:", 100, 80, 180, 98), w("GSTIN: " + BUYER, 100, 100, 400, 118),
                   w("GSTIN " + SUPPLIER, 600, 300, 900, 318)]
    assert extract_invoice([page], settings).supplier_gstin == SUPPLIER
    # your own GSTIN is never the supplier's
    settings.data["company"] = {"gstin": [SUPPLIER]}
    assert extract_invoice([_invoice_page()], settings).supplier_gstin == BUYER


def test_misread_gstin_warns_and_profile_by_gstin(tmp_path):
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    bad = SUPPLIER[:14] + ("A" if SUPPLIER[14] != "A" else "B")
    invoice = extract_invoice([_invoice_page("GSTIN : " + bad)], settings)
    assert any("fails its check" in x for x in invoice.warnings)

    settings.suppliers = [{"name": "Matched By GSTIN", "match": ["nothing on the page"], "gstin": SUPPLIER}]
    assert extract_invoice([_invoice_page()], settings).supplier_profile == "Matched By GSTIN"


def test_duplicates_by_gstin(tmp_path):
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    history = History(tmp_path / "history")
    first = extract_invoice([_invoice_page()], settings)
    history.record(first, "csv", ["a.jpg"])
    again = extract_invoice([_invoice_page()], settings)
    again.header["supplier_name"] = "Sample Garmnts Pvt"   # name misread this time
    history.record(again, "csv", ["b.jpg"])
    assert again.duplicates and again.duplicates[0]["id"] == first.scan_id
    assert history.recent(query=SUPPLIER)
