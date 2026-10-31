"""Optional item list (config/item_master.csv) used to fill values the invoice does not print.

The file is a normal CSV, for example exported from the purchase / billing software:

    SKU No./Item ID.,Article ID,Brand Name,Design Name,Size,Cup Size,Colour,M.R.P,Supplier
    NTY03140125MST,A-1001,Maybell,NIGHTWEAR,M,,Mustard,999.00,Opus Fashions

Only "SKU No./Item ID." is required. Column titles are the purchase-entry CSV titles; a few
other common names are accepted too (SKU, Item Code, MRP, ...). The SKU is matched ignoring
case, spaces and punctuation. "Supplier" (optional) limits a row to invoices of that supplier.
"""

import csv
import logging
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def lookup(index: Dict[str, List[Dict[str, str]]], sku: str, supplier_name: str) -> Optional[Dict[str, str]]:
    rows = index.get(sku_key(sku))
    if not rows:
        return None
    supplier = (supplier_name or "").lower()
    for row in rows:
        wanted = row.get("supplier", "").lower()
        if wanted and supplier and (wanted in supplier or supplier in wanted):
            return row
    general = [r for r in rows if not r.get("supplier")]
    return general[0] if general else None  # only rows for other suppliers


def apply(items: List[Dict[str, str]], path: Path, supplier_name: str, overwrite: bool) -> int:
    """Fill item values from the list. Returns the number of items found in the list."""
    index = load(path)
    if not index:
        return 0
    found = 0
    for item in items:
        row = lookup(index, item.get("sku", ""), supplier_name)
        if row is None:
            continue
        found += 1
        for field in FILLABLE:
            value = row.get(field, "")
            if value and (overwrite or not item.get(field)):
                item[field] = value
    return found
