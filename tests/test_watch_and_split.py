"""Tests for splitting a file with several invoices, and the watch folder. No OCR engine needed."""

import copy

from test_extractor import SAMPLE_SUPPLIER, garment_invoice, settings_with

from vbocr.extractor import split_pages
from vbocr.scanner import Scanner
from vbocr.watcher import FolderWatcher


def _with_number(number):
    page = garment_invoice()
    for word in page.words:
        word.text = word.text.replace("SG/25-26/0042", number)
    return page


def _continuation_page():
    page = copy.deepcopy(garment_invoice())
    page.words = [w for w in page.words if "Invoice" not in w.text and "SG/" not in w.text]
    return page


def test_split_pages_by_invoice_number(tmp_path):
    settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    a, a2, b, c = _with_number("SG/1"), _continuation_page(), _with_number("SG/2"), _with_number("SG/3")
    groups = split_pages([a, a2, b, c], settings)
    assert [len(g) for g in groups] == [2, 1, 1]
    assert len(split_pages([a, _with_number("SG/1")], settings)) == 1  # same number = same invoice


class _FakeEngine:
    def __init__(self, pages):
        self.pages = pages

    def read(self, path):
        if path.endswith("broken.jpg"):
            raise ValueError("Cannot read image broken.jpg")
        return list(self.pages)


def _scanner(tmp_path, pages):
    scanner = Scanner.__new__(Scanner)
    scanner.settings = settings_with(tmp_path, SAMPLE_SUPPLIER)
    scanner.engine = _FakeEngine(pages)
    scanner.history = None
    return scanner


def test_scan_separate_and_warning_for_pages_mode(tmp_path):
    scanner = _scanner(tmp_path, [_with_number("SG/1"), _with_number("SG/2")])
    invoices = scanner.scan_separate("two.pdf")
    assert [i.header["invoice_number"] for i in invoices] == ["SG/1", "SG/2"]
    one = scanner.scan(["two.pdf"])
    assert one.warnings[0].startswith("These 2 pages look like 2 different invoices")


def test_watch_folder(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    scanner = _scanner(tmp_path, [_with_number("SG/1"), _with_number("SG/2")])
    watcher = FolderWatcher(scanner, str(inbox))
    (inbox / "bills.pdf").write_bytes(b"%PDF")
    (inbox / "broken.jpg").write_bytes(b"x")
    (inbox / "notes.txt").write_text("not an invoice")

    assert watcher.run_once() == []  # first look: size not known to be stable yet
    written = watcher.run_once()
    assert sorted(p.split("/")[-1].split("\\")[-1] for p in written) == ["bills_1.csv", "bills_2.csv"]
    assert (inbox / "done" / "bills.pdf").exists()
    assert (inbox / "failed" / "broken.jpg").exists()
    assert "Cannot read image" in (inbox / "failed" / "broken.jpg.error.txt").read_text()
    assert (inbox / "notes.txt").exists()
    text = (inbox / "csv" / "bills_2.csv").read_text(encoding="utf-8-sig")
    assert "SG/2" in text

    (inbox / "bills.pdf").write_bytes(b"%PDF")  # same name again: nothing overwritten
    watcher.run_once()
    watcher.run_once()
    assert (inbox / "csv" / "bills_1 (2).csv").exists() and (inbox / "done" / "bills (2).pdf").exists()
