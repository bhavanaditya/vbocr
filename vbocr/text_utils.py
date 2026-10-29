"""Small helpers for cleaning up OCR text."""

import re
from datetime import datetime
from typing import Optional

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_RE = re.compile(
    r"(\d{1,2})\s*[-/.]\s*(\d{1,2}|[A-Za-z]{3,9})\s*[-/.]\s*(\d{2,4})"
)


def norm(text: str) -> str:
    """Lower-case and drop everything except letters, digits and spaces."""
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def compact(text: str) -> str:
    """Lower-case with every non-alphanumeric character removed."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def parse_date(text: str) -> Optional[datetime]:
    match = DATE_RE.search(text or "")
    if not match:
        return None
    day, month, year = match.groups()
    if month.isdigit():
        month_num = int(month)
    else:
        month_num = _MONTHS.get(month[:3].lower())
        if month_num is None:
            return None
    year_num = int(year)
    if year_num < 100:
        year_num += 2000
    try:
        return datetime(year_num, month_num, int(day))
    except ValueError:
        return None


def format_date(text: str, fmt: str) -> str:
    parsed = parse_date(text)
    return parsed.strftime(fmt) if parsed else ""


_OCR_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1", "S": "5"})


def clean_number(text: str) -> str:
    """Return a plain number string such as ``1335.32`` or an empty string."""
    if not text:
        return ""
    value = text.strip().translate(_OCR_DIGIT_FIXES)
    value = value.replace(",", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return match.group(0) if match else ""


def to_float(text: str) -> float:
    try:
        return float(clean_number(text))
    except ValueError:
        return 0.0


def clean_value(text: str) -> str:
    """Strip label separators (``:``, ``.``) and whitespace around a value."""
    return re.sub(r"^[\s:.\-]+|[\s:]+$", "", text or "")
