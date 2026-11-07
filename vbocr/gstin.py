"""GSTIN: the 15-character GST number printed on every Indian tax invoice.

    27 AAPFU0939F 1 Z V
    |  |          | | +- check character (calculated from the first 14)
    |  |          | +--- always Z
    |  |          +----- entity number (1-9, A-Z)
    |  +---------------- PAN of the business (5 letters, 4 digits, 1 letter)
    +------------------- state code (01-38, 97, 99)

The check character catches almost every misread GSTIN. OCR often mixes up O/0, I/1, S/5,
B/8, Z/2 and G/6; those are repaired only when the repaired number passes the check.

An invoice usually shows two GSTINs: the supplier's (at the top, next to the supplier's name)
and the buyer's (under "Bill to", "Buyer", "Consignee"). Your own GSTIN (company.gstin in the
settings) is never taken as the supplier's.
"""

import re
from typing import List, Optional, Tuple

from .models import Page

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CANDIDATE = re.compile(r"(?<![A-Z0-9])[0-9A-Z]{15}(?![A-Z0-9])")
# letter positions (0-based) and digit positions in a GSTIN, the rest may be either
_DIGITS = {0, 1, 7, 8, 9, 10}
_LETTERS = {2, 3, 4, 5, 6, 11}
_TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "T": "7"}
_TO_LETTER = {v: k for k, v in {"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "T": "7"}.items()}
_BUYER_WORDS = ("bill to", "billed to", "buyer", "consignee", "ship to", "shipped to", "party", "customer",
                "recipient", "sold to", "details of receiver")
_SUPPLIER_WORDS = ("supplier", "seller", "our gstin", "from")


def check_char(first14: str) -> str:
    total = 0
    for index, char in enumerate(first14):
        product = CHARS.index(char) * (2 if index % 2 else 1)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]


def is_valid(gstin: str) -> bool:
    gstin = (gstin or "").upper()
    return bool(_PATTERN.match(gstin)) and check_char(gstin[:14]) == gstin[14]


def repair(text: str) -> Tuple[str, bool]:
    """(GSTIN, valid). Fixes look-alike characters when that makes a valid GSTIN."""
    raw = re.sub(r"[^0-9A-Za-z]", "", text or "").upper()
    if len(raw) != 15:
        return raw, False
    if is_valid(raw):
        return raw, True
    fixed = list(raw)
    for index, char in enumerate(fixed):
        if index in _DIGITS and char in _TO_DIGIT:
            fixed[index] = _TO_DIGIT[char]
        elif index in _LETTERS and char in _TO_LETTER:
            fixed[index] = _TO_LETTER[char]
    if fixed[13] == "2":
        fixed[13] = "Z"
    candidate = "".join(fixed)
    if is_valid(candidate):
        return candidate, True
    # the check character itself may be misread: only accept that if everything else fits
    if _PATTERN.match(candidate):
        return candidate, False
    return raw, False


def find_all(pages: List[Page]) -> List[Tuple[str, bool, int, float, str]]:
    """Every GSTIN-like value: (gstin, valid, page index, y position (0-1), text before it)."""
    found = []
    for page_index, page in enumerate(pages):
        for word in page.words:
            text = word.text.upper()
            spaced = re.sub(r"(?<=[0-9A-Z])[\s\-.]+(?=[0-9A-Z])", "", text)
            for source in {text, spaced}:
                for match in _CANDIDATE.finditer(re.sub(r"[^0-9A-Z]", " ", source)):
                    gstin, valid = repair(match.group(0))
                    if not _PATTERN.match(gstin) and not valid:
                        continue
                    context = _line_before(page, word, source[:match.start()])
                    found.append((gstin, valid, page_index, word.cy / max(page.height, 1.0), context))
    seen = set()
    unique = []
    for entry in found:
        if entry[0] not in seen:
            seen.add(entry[0])
            unique.append(entry)
    return unique


def _line_before(page: Page, word, prefix: str) -> str:
    """Text on the same line before the GSTIN, plus the line above (labels like "Bill to")."""
    left = [w.text for w in page.words if w is not word and abs(w.cy - word.cy) < 0.6 * word.height and w.x2 <= word.x1 + 2]
    above = [w.text for w in page.words if 0 < word.cy - w.cy < 4 * word.height and abs(w.x1 - word.x1) < 6 * word.height]
    return " ".join(above[-2:] + left + [prefix]).lower()


def supplier_gstin(pages: List[Page], own_gstins: List[str]) -> Tuple[str, bool]:
    """The supplier's GSTIN: ('', False) when none was found."""
    own = {re.sub(r"[^0-9A-Z]", "", g.upper()) for g in own_gstins or []}
    candidates = [c for c in find_all(pages) if c[0] not in own]
    if not candidates:
        return "", False

    def rank(entry):
        gstin, valid, page_index, y, context = entry
        buyer = any(w in context for w in _BUYER_WORDS)
        supplier = any(w in context for w in _SUPPLIER_WORDS)
        return (buyer and not supplier, not valid, page_index, y)  # a buyer's GSTIN never wins

    best = min(candidates, key=rank)
    return best[0], best[1]


def state_code(gstin: str) -> str:
    return gstin[:2] if gstin and gstin[:2].isdigit() else ""


def pan(gstin: str) -> Optional[str]:
    return gstin[2:12] if len(gstin or "") == 15 else None
