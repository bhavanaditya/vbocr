"""Turn OCR pages into an Invoice (header values + item rows)."""

import re
from datetime import date
from typing import Any, Dict, List, Optional

from .config import Settings
from .models import ITEM_FIELDS, Invoice, Page, Table, Word
from .table import find_table
from .text_utils import clean_number, clean_value, compact, format_date, norm

DATE_FIELDS = {"po_date", "invoice_date", "lr_booking_date"}
NUMBER_FIELDS = {"invoice_number", "po_number"}
NUMERIC_ITEM_FIELDS = {"quantity", "cost_price", "mrp", "amount"}
_SKIP_NAME_WORDS = ("invoice", "tax", "bill", "original", "duplicate", "copy", "gstin", "phone", "e-mail", "email")


def extract_invoice(pages: List[Page], settings: Settings) -> Invoice:
    invoice = Invoice()
    all_text = "\n".join(p.full_text for p in pages)
    supplier = settings.match_supplier(all_text)
    invoice.supplier_profile = (supplier or {}).get("name", "")

    labels = settings.header_labels(supplier)
    date_format = settings.output.get("date_format", "%d-%m-%Y")
    found: Dict[str, str] = {}
    for page in pages:
        for field, field_labels in labels.items():
            if not found.get(field):
                found[field] = _find_labelled_value(page, field, field_labels, date_format)

    header = invoice.header
    for key in header:
        if found.get(key):
            header[key] = found[key]
    header["supplier_name"] = (supplier or {}).get("name") or _guess_supplier_name(pages[0] if pages else None)
    if settings.output.get("fill_date_with_today"):
        header["date"] = date.today().strftime(date_format)

    columns = settings.item_columns(supplier)
    default_brand = (supplier or {}).get("brand") or found.get("brand", "")
    for page_no, page in enumerate(pages, start=1):
        table = find_table(page, columns.get("serial", []))
        if table is None:
            invoice.warnings.append("Page {}: item table not found".format(page_no))
            continue
        for row in table.rows:
            invoice.items.append(_map_row(row, table, columns, settings, supplier, default_brand))

    for i, item in enumerate(invoice.items, start=1):
        missing = [f for f in ("quantity", "amount") if not item.get(f)]
        if missing:
            invoice.warnings.append("Item {}: missing {}".format(i, ", ".join(missing)))
    if not invoice.items:
        invoice.warnings.append("No items found")
    return invoice


def _find_labelled_value(page: Page, field: str, labels: List[str], date_format: str) -> str:
    words = sorted(page.words, key=lambda w: (w.y1, w.x1))
    for label in labels:
        tokens = norm(label).split()
        if not tokens:
            continue
        pattern = re.compile(r"^\W*" + r"\W*".join(re.escape(t) for t in tokens) + r"(?![a-z0-9])", re.I)
        for word in words:
            match = pattern.match(word.text)
            if not match:
                continue
            candidates = [clean_value(word.text[match.end():])]
            neighbour = _right_neighbour(page, word)
            if neighbour is not None:
                candidates.append(clean_value(neighbour.text))
            for candidate in candidates:
                value = _validate(field, candidate, date_format)
                if value:
                    return value
    return ""


def _right_neighbour(page: Page, word: Word) -> Optional[Word]:
    same_line = [
        w for w in page.words
        if w is not word
        and abs(w.cy - word.cy) < 0.6 * word.height
        and w.x1 >= word.x2 - 0.5 * word.height
        and w.x1 - word.x2 < 0.35 * page.width
    ]
    return min(same_line, key=lambda w: w.x1) if same_line else None


def _validate(field: str, value: str, date_format: str) -> str:
    if not value:
        return ""
    if field in DATE_FIELDS:
        return format_date(value, date_format)
    if field in NUMBER_FIELDS:
        return value if re.search(r"\d", value) else ""
    return value


def _guess_supplier_name(page: Optional[Page]) -> str:
    """Fallback for unknown suppliers: the largest clear text near the top."""
    if page is None:
        return ""
    top = [
        w for w in page.words
        if w.y2 < page.height * 0.2
        and w.score >= 0.9
        and len(re.sub(r"[^A-Za-z]", "", w.text)) >= 5
        and not any(s in w.text.lower() for s in _SKIP_NAME_WORDS)
    ]
    if not top:
        return ""
    return max(top, key=lambda w: w.height).text.strip()


def _map_row(
    row: Dict[str, str],
    table: Table,
    columns: Dict[str, List[str]],
    settings: Settings,
    supplier: Optional[Dict[str, Any]],
    default_brand: str,
) -> Dict[str, str]:
    titles = {compact(c.title): c.title for c in table.columns}

    def value_of(names: List[str]) -> str:
        for name in names:
            title = titles.get(compact(name))
            if title and row.get(title):
                return row[title].strip()
        return ""

    item = {f: "" for f in ITEM_FIELDS}
    for field in ("sku", "article_id", "brand", "design_name", "size", "cup_size", "colour", "cost_price", "mrp"):
        item[field] = value_of(columns.get(field, []))
    item["quantity"] = value_of(settings.output.get("quantity_priority", []))
    item["amount"] = value_of(settings.output.get("amount_priority", []))
    item["sku"] = item["sku"].replace(" ", "")

    description = value_of(columns.get("description", []))
    if description:
        for pattern in settings.description_patterns(supplier):
            match = re.match(pattern, description)
            if match:
                for key, val in match.groupdict().items():
                    if key in item and val and not item[key]:
                        item[key] = val.strip()
                break
        else:
            if not item["design_name"]:
                item["design_name"] = description

    if not item["brand"]:
        item["brand"] = default_brand
    suffix_len = int((supplier or {}).get("colour_from_sku_suffix") or 0)
    if not item["colour"] and suffix_len and len(item["sku"]) > suffix_len:
        code = item["sku"][-suffix_len:].upper()
        item["colour"] = settings.colour_codes.get(code, code)

    for field in NUMERIC_ITEM_FIELDS:
        item[field] = clean_number(item[field])
    return item
