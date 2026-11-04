"""The samples test bench: CSV comparison (fast), and your own samples (slow, real OCR).

Your samples run only with VBOCR_OCR_TESTS=1 (see vbocr/samples.py):
    set VBOCR_OCR_TESTS=1 && python -m pytest tests/test_samples.py
"""

import os
from pathlib import Path

import pytest
from test_extractor import SAMPLE_SUPPLIER, garment_invoice, settings_with

from vbocr import samples
from vbocr.config import ROOT_DIR
from vbocr.csv_output import invoice_to_csv
from vbocr.extractor import extract_invoice


def test_compare_with_expected_csv(tmp_path):
    invoice = extract_invoice([garment_invoice()], settings_with(tmp_path, SAMPLE_SUPPLIER))
    expected = invoice_to_csv(invoice, True)
    header, items = samples.read_csv("﻿" + expected)
    assert header["invoice_number"] == "SG/25-26/0042" and len(items) == 3
    assert samples.compare(invoice, expected)["differences"] == []

    wrong = expected.replace("1335.32", "1335.33").replace("SG/25-26/0042", "SG/25-26/0024")
    result = samples.compare(invoice, wrong)
    assert len(result["differences"]) == 2 and result["right"] == result["checked"] - 2
    assert any(d.startswith("item 1 Amount") for d in result["differences"])

    excel = expected.replace("05-02-2026", "05/02/2026").encode("cp1252")
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "expected.csv").write_bytes(excel)
    assert samples.compare(invoice, samples.read_expected(tmp_path / "s"))["differences"] == []

    invoice.items.pop()
    assert "items: got 2 rows, expected 3" in samples.compare(invoice, expected)["differences"]


SAMPLES = Path(os.environ.get("VBOCR_SAMPLES") or ROOT_DIR / "samples")


@pytest.mark.skipif(os.environ.get("VBOCR_OCR_TESTS") != "1", reason="set VBOCR_OCR_TESTS=1 to run")
@pytest.mark.parametrize("sample", samples.sample_dirs(SAMPLES), ids=lambda p: p.name)
def test_your_samples(sample):
    from vbocr.config import Settings
    from vbocr.scanner import Scanner

    global _scanner
    if "_scanner" not in globals():
        _scanner = Scanner(Settings(), record_history=False)
    invoice = _scanner.scan(samples.sample_pages(sample))
    result = samples.compare(invoice, samples.read_expected(sample))
    assert result["differences"] == []
