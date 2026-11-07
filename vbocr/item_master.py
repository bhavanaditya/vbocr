"""Optional item list (config/item_master.csv) used to fill values the invoice does not print.

The file is a normal CSV, for example exported from the purchase / billing software:

    SKU No./Item ID.,Article ID,Brand Name,Design Name,Size,Cup Size,Colour,M.R.P,Supplier
    NTY03140125MST,A-1001,Maybell,NIGHTWEAR,M,,Mustard,999.00,Opus Fashions

Only "SKU No./Item ID." is required. Column titles are the purchase-entry CSV titles; a few
other common names are accepted too (SKU, Item Code, MRP, ...). The SKU is matched ignoring
case, spaces and punctuation. "Supplier" (optional) limits a row to invoices of that supplier.

Values the user corrects in the browser are also remembered, in item_master.learned.csv (same
layout). The main file always wins over the learned one.
"""

import csv
import logging
import re
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .text_utils import to_float

log = logging.getLogger(__name__)

FILLABLE = ["article_id", "brand", "design_name", "size", "cup_size", "colour", "cost_price", "mrp"]

_COLUMN_NAMES = {
    "sku": ["sku no./item id.", "sku no", "sku", "item id", "item code", "sku code", "barcode", "style no"],
    "article_id": ["article id", "article", "article no", "art no"],
    "brand": ["brand name", "brand"],
    "design_name": ["design name", "design", "item name", "description"],
    "size": ["size"],
    "cup_size": ["cup size", "cup"],
    "colour": ["colour", "color", "shade"],
    "cost_price": ["cost price", "cost", "purchase price", "rate"],
    "mrp": ["m.r.p", "mrp", "m r p", "retail price"],
    "supplier": ["supplier", "supplier name", "vendor"],
}

_cache: Dict[str, Tuple[float, Dict[str, List[Dict[str, str]]]]] = {}
_lock = threading.Lock()


def sku_key(sku: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (sku or "").upper())


def load(path: Path) -> Dict[str, List[Dict[str, str]]]:
    """SKU key -> rows. Re-read automatically when the file changes. Missing file = empty."""
    if not path.is_file():
        return {}
    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
        index = _read(path)
        _cache[str(path)] = (mtime, index)
        log.info("Item list %s: %d SKUs", path, len(index))
        return index


def _read(path: Path) -> Dict[str, List[Dict[str, str]]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(text.splitlines(), dialect)
    rows = list(reader)
    if not rows:
        return {}
    titles = [re.sub(r"\s+", " ", t.strip().lower()) for t in rows[0]]
    columns: Dict[str, int] = {}
    for field, names in _COLUMN_NAMES.items():
        for name in names:
            if name in titles:
                columns[field] = titles.index(name)
                break
    if "sku" not in columns:
        log.warning("Item list %s has no SKU column (expected 'SKU No./Item ID.' or 'SKU')", path)
        return {}

    index: Dict[str, List[Dict[str, str]]] = {}
    for values in rows[1:]:
        record = {f: (values[i].strip() if i < len(values) else "") for f, i in columns.items()}
        key = sku_key(record.get("sku", ""))
        if key:
            index.setdefault(key, []).append(record)
    return index


def lookup(
    index: Dict[str, List[Dict[str, str]]], sku: str, supplier_name: str, supplier_gstin: str = ""
) -> Optional[Dict[str, str]]:
    """The row for this SKU: one for this supplier (by name, or by GSTIN), else a general one."""
    rows = index.get(sku_key(sku))
    if not rows:
        return None
    supplier = (supplier_name or "").lower()
    gstin = (supplier_gstin or "").lower()
    for row in rows:
        wanted = row.get("supplier", "").lower()
        if wanted and gstin and wanted == gstin:
            return row
        if wanted and supplier and (wanted in supplier or supplier in wanted):
            return row
    general = [r for r in rows if not r.get("supplier")]
    return general[0] if general else None  # only rows for other suppliers


NUMERIC = {"cost_price", "mrp"}
TITLES = {"sku": "SKU No./Item ID.", "article_id": "Article ID", "brand": "Brand Name",
          "design_name": "Design Name", "size": "Size", "cup_size": "Cup Size", "colour": "Colour",
          "cost_price": "Cost Price", "mrp": "M.R.P", "supplier": "Supplier"}


def _same(field: str, a: str, b: str) -> bool:
    if field in NUMERIC:
        return abs(to_float(a) - to_float(b)) < 0.005
    return sku_key(a) == sku_key(b)


def apply(
    items: List[Dict[str, str]], paths: Iterable[Path], supplier_name: str, overwrite: bool,
    supplier_gstin: str = "",
) -> Tuple[int, List[Tuple[int, str]]]:
    """Fill item values from the item list(s), first file first.

    Returns (number of items found in a list, [(item index, field), ...] where the invoice
    shows a different value than the list: worth a second look)."""
    found = set()
    conflicts: List[Tuple[int, str]] = []
    for number, path in enumerate(paths):
        index = load(Path(path))
        if not index:
            continue
        for position, item in enumerate(items):
            row = lookup(index, item.get("sku", ""), supplier_name, supplier_gstin)
            if row is None:
                continue
            found.add(position)
            for field in FILLABLE:
                value = row.get(field, "")
                if not value:
                    continue
                current = item.get(field, "")
                if not current or (overwrite and number == 0):
                    item[field] = value
                elif not _same(field, current, value) and (position, field) not in conflicts:
                    conflicts.append((position, field))
    return len(found), conflicts


_learn_lock = threading.Lock()


def learn(path: Path, supplier: str, original: List[Dict[str, str]], items: List[Dict[str, str]]) -> int:
    """Remember item values the user typed or corrected (by SKU and supplier), so the next
    invoice with that SKU gets them filled in. ``supplier`` is the supplier's GSTIN when known
    (exact), else the supplier name as read from the invoice. Returns the number of values learned."""
    from .history import match_rows

    learned: Dict[str, Dict[str, str]] = {}
    for item, index in zip(items, match_rows(original, items)):
        key = sku_key(item.get("sku", ""))
        if not key:
            continue
        before = original[index] if index is not None else {}
        values = {f: item.get(f, "").strip() for f in FILLABLE
                  if item.get(f, "").strip() and item.get(f, "") != before.get(f, "")}
        if values:
            learned.setdefault(key, {"sku": item["sku"].strip()}).update(values)
    if not learned:
        return 0

    with _learn_lock:
        rows: List[Dict[str, str]] = []
        if path.is_file():
            for entries in _read(path).values():
                rows.extend(entries)
        supplier = (supplier or "").strip()
        count = 0
        for key, values in learned.items():
            target = next((r for r in rows if sku_key(r.get("sku", "")) == key
                           and r.get("supplier", "").lower() == supplier.lower()), None)
            if target is None:
                target = {"sku": values["sku"], "supplier": supplier}
                rows.append(target)
            for field, value in values.items():
                if field != "sku":
                    target[field] = value
                    count += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = ["sku"] + FILLABLE + ["supplier"]
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([TITLES[c] for c in columns])
            for row in rows:
                writer.writerow([row.get(c, "") for c in columns])
        _cache.pop(str(path), None)
        log.info("Item list: learned %d value(s) into %s", count, path)
        return count
