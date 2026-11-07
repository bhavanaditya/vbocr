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


def test_watch_folder_file_still_open_is_scanned_once(tmp_path, monkeypatch):
    """Windows: the scanner program (or antivirus) still has the file open, so it cannot be
    moved to done. It must not be scanned again and again; only the move is retried."""
    import os

    from vbocr import watcher as watcher_module

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    scanner = _scanner(tmp_path, [_with_number("SG/7")])
    calls = []
    real_scan = scanner.scan_separate
    monkeypatch.setattr(scanner, "scan_separate", lambda *a: calls.append(a) or real_scan(*a))
    locked = {"on": True}
    real_replace = os.replace

    def replace(src, dst):
        if locked["on"] and src.endswith("bill.jpg"):
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return real_replace(src, dst)

    monkeypatch.setattr(watcher_module.os, "replace", replace)
    w = FolderWatcher(scanner, str(inbox))
    (inbox / "bill.jpg").write_bytes(b"jpeg")
    for _ in range(6):
        w.run_once()
    assert len(calls) == 1                                    # scanned once, not every 3 seconds
    assert len(list((inbox / "csv").glob("*.csv"))) == 1
    assert (inbox / "bill.jpg").exists()
    assert not (inbox / "done").exists() or not list((inbox / "done").iterdir())  # no copy left behind

    locked["on"] = False                                      # the other program closed it
    w.run_once()
    assert (inbox / "done" / "bill.jpg").exists() and not (inbox / "bill.jpg").exists()
    assert len(calls) == 1

    (inbox / "bill.jpg").write_bytes(b"new jpeg")             # a new file with the same name
    w.run_once()
    w.run_once()
    assert len(calls) == 2
