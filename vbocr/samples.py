"""Test bench with your own invoices: check that reading stays right after changes.

    samples/                       (not in git: invoices are business data)
      opus-2026-001/
        page1.jpg                  the invoice page(s), in page order (sorted by name)
        expected.csv               the correct purchase-entry CSV for it
      fabric-photo/
        bill.pdf
        expected.csv

    python -m vbocr add-sample C:\\Invoices\\bill.jpg --name opus-2026-001
        copies the file(s), scans them and saves the result as expected.csv. Open it in
        Excel, correct every wrong value, save (keep the CSV format).

    python -m vbocr check-samples
        scans every sample again and lists each value that differs from expected.csv.
"""

import csv
import io
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .csv_output import HEADER_TITLES, ITEM_TITLES
from .engine import SUPPORTED_EXTENSIONS
from .models import HEADER_FIELDS, ITEM_FIELDS
from .text_utils import parse_date, to_float

EXPECTED = "expected.csv"
NUMERIC = {"quantity", "cost_price", "mrp", "amount"}
DATES = {"date", "po_date", "lr_booking_date", "stock_received_date", "invoice_date"}


def read_expected(sample: Path) -> str:
    """expected.csv as text. Excel may have saved it as UTF-8 or as Windows text."""
    raw = (sample / EXPECTED).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def sample_dirs(folder: Path) -> List[Path]:
    if not folder.is_dir():
        return []
    return sorted(d for d in folder.iterdir() if d.is_dir() and (d / EXPECTED).is_file())


def sample_pages(sample: Path) -> List[str]:
    return [str(p) for p in sorted(sample.iterdir(), key=lambda p: p.name.lower())
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]


def add_sample(scanner, files: List[str], folder: Path, name: Optional[str] = None) -> Path:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name or Path(files[0]).stem).strip("-") or "sample"
    target = folder / name
    n = 1
    while target.exists():
        n += 1
        target = folder / "{}-{}".format(name, n)
    target.mkdir(parents=True)
    for index, path in enumerate(files, start=1):
        prefix = "page{:02d}_".format(index) if len(files) > 1 else ""
        shutil.copy2(path, target / (prefix + Path(path).name))
    invoice = scanner.scan(sample_pages(target))
    with open(target / EXPECTED, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(scanner.to_csv(invoice))
    return target


def read_csv(text: str) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """Purchase-entry CSV -> (header values, items), keyed by field name."""
    rows = [r for r in csv.reader(io.StringIO(text.lstrip("\ufeff")))]
    header: Dict[str, str] = {}
    items: List[Dict[str, str]] = []
    titles_to_header = {t.lower(): f for t, f in zip(HEADER_TITLES, HEADER_FIELDS)}
    titles_to_item = {t.lower(): f for t, f in zip(ITEM_TITLES[1:], ITEM_FIELDS)}
    i = 0
    while i < len(rows):
        row = [c.strip() for c in rows[i]]
        lowered = [c.lower() for c in row]
        if "invoice number" in lowered and i + 1 < len(rows):
            values = rows[i + 1]
            for col, title in enumerate(lowered):
                if title in titles_to_header and col < len(values):
                    header[titles_to_header[title]] = values[col].strip()
            i += 2
            continue
        if "sku no./item id." in lowered:
            columns = [(col, titles_to_item[t]) for col, t in enumerate(lowered) if t in titles_to_item]
            for values in rows[i + 1:]:
                if not values or not any(v.strip() for v in values) or values[0].strip().lower() == "total":
                    break
                items.append({field: (values[col].strip() if col < len(values) else "") for col, field in columns})
            break
        i += 1
    return header, items


def _same(field: str, got: str, want: str) -> bool:
    if field in NUMERIC and (got or want):
        return abs(to_float(got) - to_float(want)) < 0.005
    if field in DATES and got and want:
        a, b = parse_date(got), parse_date(want)  # Excel may save 05-02-2026 as 05/02/2026
        if a and b:
            return a == b
    return re.sub(r"\s+", " ", got or "").strip().lower() == re.sub(r"\s+", " ", want or "").strip().lower()


def compare(invoice, expected_text: str) -> Dict:
    """Differences between a scan and the expected CSV."""
    want_header, want_items = read_csv(expected_text)
    differences = []
    checked = right = 0
    for field, want in want_header.items():
        if field in ("date", "grn_number", "stock_received_date"):
            continue  # filled in by hand, not read from the invoice
        got = invoice.header.get(field, "")
        checked += 1
        if _same(field, got, want):
            right += 1
        else:
            differences.append("{}: got {!r}, expected {!r}".format(HEADER_TITLES[HEADER_FIELDS.index(field)], got, want))
    if len(invoice.items) != len(want_items):
        differences.append("items: got {} rows, expected {}".format(len(invoice.items), len(want_items)))
    for row, want in enumerate(want_items, start=1):
        got_item = invoice.items[row - 1] if row <= len(invoice.items) else {}
        for field, value in want.items():
            checked += 1
            got = got_item.get(field, "")
            if _same(field, got, value):
                right += 1
            else:
                differences.append("item {} {}: got {!r}, expected {!r}".format(
                    row, ITEM_TITLES[ITEM_FIELDS.index(field) + 1], got, value))
    return {"checked": checked, "right": right, "differences": differences}


def check_samples(scanner, folder: Path, report=print) -> int:
    """Scan every sample and report differences. Returns the number of samples that differ."""
    samples = sample_dirs(folder)
    if not samples:
        report("No samples in {}. Add one with:  python -m vbocr add-sample <invoice file(s)> --name <name>".format(folder))
        return 0
    failed = 0
    total_checked = total_right = 0
    for sample in samples:
        pages = sample_pages(sample)
        try:
            invoice = scanner.scan(pages)
        except Exception as error:  # noqa: BLE001
            failed += 1
            report("FAIL  {}: {}: {}".format(sample.name, type(error).__name__, error))
            continue
        result = compare(invoice, read_expected(sample))
        total_checked += result["checked"]
        total_right += result["right"]
        if result["differences"]:
            failed += 1
            report("FAIL  {}  ({}/{} values right)".format(sample.name, result["right"], result["checked"]))
            for line in result["differences"][:15]:
                report("        " + line)
            if len(result["differences"]) > 15:
                report("        ... and {} more".format(len(result["differences"]) - 15))
        else:
            report("OK    {}  ({} values)".format(sample.name, result["checked"]))
    share = 100.0 * total_right / total_checked if total_checked else 100.0
    report("{} of {} samples fully right; {:.1f}% of all values right.".format(
        len(samples) - failed, len(samples), share))
    return failed
