"""End-to-end test with the real OCR engine (slow: loads PaddleOCR).

Runs only when VBOCR_OCR_TESTS=1, e.g. in the Windows CI:
    set VBOCR_OCR_TESTS=1 && python -m pytest tests/test_ocr_end_to_end.py
"""

import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("VBOCR_OCR_TESTS") != "1", reason="set VBOCR_OCR_TESTS=1 to run")

EXPECTED_AMOUNTS = ["1335.32", "801.32", "2604.46"]


@pytest.fixture(scope="module")
def scanner(tmp_path_factory):
    from vbocr.config import Settings
    from vbocr.scanner import Scanner

    settings = Settings()
    settings.data["history"] = {"enabled": True, "folder": str(tmp_path_factory.mktemp("history"))}
    settings.data["watch"] = {}
    return Scanner(settings)


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    from make_test_files import make_all

    folder = tmp_path_factory.mktemp("files")
    make_all(folder)
    return folder


@pytest.mark.parametrize("name", ["a_bill.jpg", "b_bill.png", "photo/angled.jpg", "photo/upside_down.jpg"])
def test_image(scanner, files, name):
    invoice = scanner.scan([str(files / name)])
    assert invoice.header["invoice_number"] == "SG/25-26/0042"
    assert invoice.header["invoice_date"] == "05-02-2026"
    assert [i["amount"] for i in invoice.items] == EXPECTED_AMOUNTS
    assert [i["quantity"] for i in invoice.items] == ["2", "1", "3"]
    assert invoice.total_check["status"] == "mismatch"  # prints 5743.10 on purpose
    assert invoice.source == "ocr"


def test_digital_pdf(scanner, files):
    invoice = scanner.scan([str(files / "digital-invoice.pdf")])
    assert invoice.source == "pdf-text"
    assert [i["amount"] for i in invoice.items] == EXPECTED_AMOUNTS
    assert invoice.total_check["status"] == "ok"


def test_two_invoices_in_one_pdf(scanner, files):
    invoices = scanner.scan_separate(str(files / "two-invoices.pdf"))
    assert [i.header["invoice_number"] for i in invoices] == ["SG/25-26/0042", "SG/25-26/0043"]


def test_damaged_file(scanner, files):
    with pytest.raises(ValueError, match="Cannot read image"):
        scanner.scan([str(files / "c_bad.png")])
