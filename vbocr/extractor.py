"""Turn OCR pages into an Invoice (header values + item rows)."""

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from . import gstin as gst
from . import item_master
from .config import Settings
from .models import ITEM_FIELDS, Invoice, Page, Table, Word
from .table import find_table
from .text_utils import clean_number, clean_value, compact, format_date, norm, number_was_fixed, to_float

DATE_FIELDS = {"po_date", "invoice_date", "lr_booking_date"}
NUMBER_FIELDS = {"invoice_number", "po_number"}
NUMERIC_ITEM_FIELDS = {"quantity", "cost_price", "mrp", "amount"}
_SKIP_NAME_WORDS = ("invoice", "tax", "bill", "original", "duplicate", "copy", "gstin", "phone", "e-mail", "email")


def extract_invoice(pages: List[Page], settings: Settings) -> Invoice:
    invoice = Invoice()
    all_text = "\n".join(p.full_text for p in pages)
    supplier_gstin, gstin_valid = gst.supplier_gstin(pages, settings.own_gstins)
    invoice.supplier_gstin = supplier_gstin
    if supplier_gstin and not gstin_valid:
        invoice.warnings.append(
            "Supplier GSTIN {} fails its check character: a character is probably misread.".format(supplier_gstin))
    supplier = settings.match_supplier(all_text, supplier_gstin if gstin_valid else "")
    invoice.supplier_profile = (supplier or {}).get("name", "")

    labels = settings.header_labels(supplier)
    date_format = settings.output.get("date_format", "%d-%m-%Y")
    found: Dict[str, str] = {}
    found_scores: Dict[str, float] = {}
    for page in pages:
        for field, field_labels in labels.items():
            if not found.get(field):
                found[field], found_scores[field] = _find_labelled_value(page, field, field_labels, date_format)

    header = invoice.header
    for key in header:
        if found.get(key):
            header[key] = found[key]
    if supplier:
        header["supplier_name"] = supplier.get("name") or ""
    else:
        header["supplier_name"], found_scores["supplier_name"] = _guess_supplier_name(pages[0] if pages else None)
    if settings.output.get("fill_date_with_today"):
        header["date"] = date.today().strftime(date_format)

    columns = settings.item_columns(supplier)
    default_brand = (supplier or {}).get("brand") or found.get("brand", "")
    item_scores: List[Dict[str, float]] = []
    for page_no, page in enumerate(pages, start=1):
        table = find_table(page, columns.get("serial", []))
        if table is None:
            invoice.warnings.append("Page {}: item table not found".format(page_no))
            continue
        for row_no, row in enumerate(table.rows):
            row_scores = table.scores[row_no] if row_no < len(table.scores) else {}
            item, scores = _map_row(row, row_scores, table, columns, settings, supplier, default_brand)
            invoice.items.append(item)
            item_scores.append(scores)

    # Items from the optional item list: fill values the invoice does not print.
    master = settings.item_master
    lists = [settings.resolve(master[k]) for k in ("file", "learned_file") if master.get(k)]
    if lists and invoice.items:
        _, conflicts = item_master.apply(invoice.items, lists, header["supplier_name"], bool(master.get("overwrite")),
                                         invoice.supplier_gstin if gstin_valid else "")
        for index, field in conflicts:  # the invoice differs from your item list: check it
            if index < len(item_scores):
                item_scores[index][field] = 0.0

    _mark_unsure(invoice, found_scores, item_scores, settings)
    invoice.total_check = check_total(pages, invoice, settings)
    if invoice.total_check.get("status") == "mismatch":
        invoice.warnings.append(invoice.total_check["message"])

    for i, item in enumerate(invoice.items, start=1):
        missing = [f for f in ("quantity", "amount") if not item.get(f)]
        if missing:
            invoice.warnings.append("Item {}: missing {}".format(i, ", ".join(missing)))
    if not invoice.items:
        invoice.warnings.append("No items found")
    return invoice


def split_pages(pages: List[Page], settings: Settings) -> List[List[Page]]:
    """Group the pages of one file into invoices: a page whose invoice number differs from the
    current invoice's starts a new one. Pages without a number (continuation pages) stay with
    the invoice before them."""
    date_format = settings.output.get("date_format", "%d-%m-%Y")
    groups: List[List[Page]] = []
    current = ""
    for page in pages:
        supplier = settings.match_supplier(page.full_text)
        labels = settings.header_labels(supplier).get("invoice_number") or []
        number = compact(_find_labelled_value(page, "invoice_number", labels, date_format)[0])
        if not groups or (number and current and number != current):
            groups.append([page])
        else:
            groups[-1].append(page)
        if number:
            current = number
    return groups


def _mark_unsure(
    invoice: Invoice, header_scores: Dict[str, float], item_scores: List[Dict[str, float]], settings: Settings
) -> None:
    """List the values the OCR was not sure about, so the user checks those first."""
    limit = float(settings.checks.get("min_confidence", 0.9))
    for field, score in header_scores.items():
        if field in invoice.header and invoice.header[field] and score < limit:
            invoice.unsure.append({"row": 0, "field": field})
    for row_no, scores in enumerate(item_scores, start=1):
        for field, score in scores.items():
            if score < limit and invoice.items[row_no - 1].get(field):
                invoice.unsure.append({"row": row_no, "field": field})


_NUMBER_WORD_RE = re.compile(r"^[^\dA-Za-z]{0,4}(?:Rs\.?|INR)?\s*[\d,]+(?:\.\d{1,2})?\s*(?:/-)?$")
_GST_RATES = (0.05, 0.12, 0.18, 0.28, 0.03)


def check_total(pages: List[Page], invoice: Invoice, settings: Settings) -> Dict[str, object]:
    """Compare the sum of the item amounts with the total printed on the invoice.

    Returns {"status": "ok" | "mismatch" | "not_found" | "no_items", "items_total": ..,
    "printed_total": .., "label": .., "message": ..}.
    """
    amounts = [to_float(i.get("amount", "")) for i in invoice.items]
    if not invoice.items or not any(amounts):
        return {"status": "no_items"}
    items_total = round(sum(amounts), 2)
    tolerance = float(settings.checks.get("total_tolerance", 1.0))
    labels = [norm(l) for l in settings.checks.get("total_labels") or [] if norm(l)]

    candidates = []  # (label priority, label, value)
    for page in reversed(pages):
        for word in page.words:
            text = norm(word.text)
            for priority, label in enumerate(labels):
                if not (text == label or text.startswith(label + " ")):
                    continue
                values = []
                rest = re.sub(r"(?i)^.*?" + r"\W*".join(re.escape(t) for t in label.split()), "", word.text, count=1)
                if _NUMBER_WORD_RE.match(rest.strip(" :")):
                    values.append(to_float(rest))
                for other in page.words:
                    if other is word or other.x1 < word.x2 - 0.5 * word.height:
                        continue
                    if abs(other.cy - word.cy) < 0.6 * max(word.height, other.height) and _NUMBER_WORD_RE.match(other.text.strip()):
                        values.append(to_float(other.text))
                candidates.extend((priority, word.text.strip(), v) for v in values if v > 0)
                break

    if not candidates:
        return {"status": "not_found", "items_total": "{:.2f}".format(items_total)}

    for _, label, value in candidates:
        if abs(value - items_total) <= tolerance:
            return {"status": "ok", "items_total": "{:.2f}".format(items_total),
                    "printed_total": "{:.2f}".format(value), "label": label}
    adjustments = _find_adjustments(pages, settings)
    for _, label, value in candidates:
        explained = _explain_difference(value - items_total, adjustments, tolerance)
        if explained is not None:
            return {"status": "ok", "items_total": "{:.2f}".format(items_total),
                    "printed_total": "{:.2f}".format(value), "label": label,
                    "expected_items_total": "{:.2f}".format(value - sum(v for _, v in explained)),
                    "note": "printed total = items" + "".join(
                        " {} {} {:,.2f}".format("-" if v < 0 else "+", n, abs(v)) for n, v in explained),
                    "adjustments": [{"label": n, "value": "{:.2f}".format(v)} for n, v in explained]}
    for _, label, value in candidates:
        for rate in _GST_RATES:
            if abs(value - items_total * (1 + rate)) <= tolerance + 0.01 * items_total * 0.01:
                return {"status": "ok", "items_total": "{:.2f}".format(items_total),
                        "printed_total": "{:.2f}".format(value), "label": label,
                        "expected_items_total": "{:.2f}".format(value / (1 + rate)),
                        "note": "printed total includes {:g}% GST".format(rate * 100)}

    best = min(candidates, key=lambda c: (c[0], -c[2]))
    message = (
        "Total check: the items add up to {:,.2f} but the invoice shows {:,.2f} ({}). "
        "A row may be missing or misread.".format(items_total, best[2], best[1])
    )
    return {"status": "mismatch", "items_total": "{:.2f}".format(items_total),
            "printed_total": "{:.2f}".format(best[2]), "label": best[1], "message": message}


_SIGNED_NUMBER_RE = re.compile(r"^(?P<sign>\(-\)|-|\(?less\)?)?\s*(?:Rs\.?|INR|₹)?\s*(?P<num>[\d,]+(?:\.\d{1,2})?)\s*(?:/-)?\)?$", re.I)


def _find_adjustments(pages: List[Page], settings: Settings) -> List[Tuple[str, float]]:
    """Tax, charge and discount lines near the total: ("CGST", 120.0), ("Discount", -50.0), ...
    A number printed with % (the rate) is not an amount."""
    checks = settings.checks
    kinds = [(l, 1) for l in checks.get("tax_labels") or []] + [(l, 1) for l in checks.get("charge_labels") or []]
    kinds += [(l, -1) for l in checks.get("discount_labels") or []]
    found: List[Tuple[str, float]] = []
    seen = set()
    for page in pages:
        for word in page.words:
            tokens = norm(word.text).split()
            for label, sign in kinds:
                label_tokens = norm(label).split()
                if not label_tokens or not _starts_with_label(tokens, label_tokens):
                    continue
                value = _amount_on_line(page, word)
                if value is None:
                    break
                amount = sign * abs(value) if sign < 0 or value >= 0 else value
                key = (label.lower(), round(amount, 2))
                if amount and key not in seen:
                    seen.add(key)
                    found.append((label.upper() if len(label) <= 5 else label.capitalize(), amount))
                break
    return found[:8]


def _starts_with_label(tokens: List[str], label: List[str]) -> bool:
    """'Add CGST @ 2.5%' and 'CGST' both start with the label CGST (after Add / Less)."""
    while tokens and tokens[0] in ("add", "less", "by", "to"):
        tokens = tokens[1:]
    return tokens[:len(label)] == label


def _amount_on_line(page: Page, word: Word) -> Optional[float]:
    """The right-most amount on the label's line (signed), ignoring rates like '2.5%'."""
    best = None
    inline = re.split(r"[:=]", word.text, maxsplit=1)
    parts = [(word.x2, inline[1].strip())] if len(inline) == 2 else []
    for other in page.words:
        if other is word or other.x1 < word.x2 - 0.5 * word.height:
            continue
        if abs(other.cy - word.cy) < 0.6 * max(word.height, other.height):
            parts.append((other.x2, other.text.strip()))
    for x, text in sorted(parts):
        if "%" in text:
            continue
        match = _SIGNED_NUMBER_RE.match(text)
        if match:
            value = to_float(match.group("num"))
            best = -value if match.group("sign") else value
    return best


def _explain_difference(difference: float, adjustments: List[Tuple[str, float]], tolerance: float):
    """The smallest set of adjustments that adds up to the difference, or None."""
    from itertools import combinations

    if not adjustments:
        return None
    for size in range(1, len(adjustments) + 1):
        for combo in combinations(adjustments, size):
            if abs(sum(v for _, v in combo) - difference) <= tolerance:
                return list(combo)
    return None


def _find_labelled_value(page: Page, field: str, labels: List[str], date_format: str) -> Tuple[str, float]:
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
            candidates = [(clean_value(word.text[match.end():]), word.score)]
            neighbour = _right_neighbour(page, word)
            if neighbour is not None:
                candidates.append((clean_value(neighbour.text), neighbour.score))
            for candidate, score in candidates:
                value = _validate(field, candidate, date_format)
                if value:
                    return value, score
    return "", 1.0


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


def _guess_supplier_name(page: Optional[Page]) -> Tuple[str, float]:
    """Fallback for unknown suppliers: the largest clear text near the top."""
    if page is None:
        return "", 1.0
    top = [
        w for w in page.words
        if w.y2 < page.height * 0.2
        and w.score >= 0.9
        and len(re.sub(r"[^A-Za-z]", "", w.text)) >= 5
        and not any(s in w.text.lower() for s in _SKIP_NAME_WORDS)
    ]
    if not top:
        return "", 1.0
    best = max(top, key=lambda w: w.height)
    return best.text.strip(), best.score


def _map_row(
    row: Dict[str, str],
    row_scores: Dict[str, float],
    table: Table,
    columns: Dict[str, List[str]],
    settings: Settings,
    supplier: Optional[Dict[str, Any]],
    default_brand: str,
) -> Tuple[Dict[str, str], Dict[str, float]]:
    """One table row -> (item values, OCR confidence per item field)."""
    titles = {compact(c.title): c.title for c in table.columns}
    scores: Dict[str, float] = {}

    def value_of(names: List[str], field: str = "") -> str:
        for name in names:
            title = titles.get(compact(name))
            if title and row.get(title):
                if field:
                    scores[field] = row_scores.get(title, 1.0)
                return row[title].strip()
        return ""

    item = {f: "" for f in ITEM_FIELDS}
    for field in ("sku", "article_id", "brand", "design_name", "size", "cup_size", "colour", "cost_price", "mrp"):
        item[field] = value_of(columns.get(field, []), field)
    item["quantity"] = value_of(settings.output.get("quantity_priority", []), "quantity")
    item["amount"] = value_of(settings.output.get("amount_priority", []), "amount")
    item["sku"] = item["sku"].replace(" ", "")

    description = value_of(columns.get("description", []), "description")
    if description:
        for pattern in settings.description_patterns(supplier):
            match = re.match(pattern, description)
            if match:
                for key, val in match.groupdict().items():
                    if key in item and val and not item[key]:
                        item[key] = val.strip()
                        scores[key] = scores.get("description", 1.0)
                break
        else:
            if not item["design_name"]:
                item["design_name"] = description
                scores["design_name"] = scores.get("description", 1.0)
    scores.pop("description", None)

    if not item["brand"]:
        item["brand"] = default_brand
    suffix_len = int((supplier or {}).get("colour_from_sku_suffix") or 0)
    if not item["colour"] and suffix_len and len(item["sku"]) > suffix_len:
        code = item["sku"][-suffix_len:].upper()
        item["colour"] = settings.colour_codes.get(code, code)
        if "sku" in scores:
            scores["colour"] = scores["sku"]

    for field in NUMERIC_ITEM_FIELDS:
        if number_was_fixed(item[field]):
            scores[field] = min(scores.get(field, 1.0), 0.5)  # letters read as digits: check it
        item[field] = clean_number(item[field])
    return item, scores
