"""Rebuild the item table of an invoice from loose OCR text boxes.

The approach works for most printed invoices without per-supplier code:

1. Find the serial-number header cell ("S.No", "Sl.No", ...). The other
   header cells on the same band become the table columns. Headers printed
   on two lines ("Total" / "Qty") are merged into one column.
2. Every integer found under the serial-number header starts an item row.
3. Cells are assigned to rows column by column, from left to right. The
   expected row position is carried over from the previous column, so a
   photo taken at a slight angle still lines up.
4. A text box that the OCR engine merged across two empty columns
   (e.g. ``NIGHTWEAR62082100``) is split back into its parts.
"""

import re
import statistics
from typing import Dict, List, Optional, Sequence

from .models import Column, Page, Table, Word
from .text_utils import compact

_SERIAL_VALUE_RE = re.compile(r"^\D{0,2}(\d{1,4})\D{0,2}$")


def find_table(page: Page, serial_headers: Sequence[str]) -> Optional[Table]:
    serial_keys = {compact(h) for h in serial_headers}
    candidates = [w for w in page.words if compact(w.text) in serial_keys]
    best: Optional[Table] = None
    for serial_word in candidates:
        table = _build_table(page, serial_word)
        if table and (best is None or len(table.rows) > len(best.rows)):
            best = table
    return best


def _build_table(page: Page, serial_word: Word) -> Optional[Table]:
    columns = _header_columns(page, serial_word)
    if len(columns) < 3:
        return None
    serial_col = next(c for c in columns if c.x1 <= serial_word.cx <= c.x2)
    header_bottom = max(serial_word.y2, serial_word.cy)

    anchors = _row_anchors(page, serial_col, header_bottom)
    if not anchors:
        return None

    gaps = [b.cy - a.cy for a, b in zip(anchors, anchors[1:])]
    row_height = statistics.median(gaps) if gaps else serial_word.height * 1.6

    cells = _assign_cells(page, columns, serial_col, anchors, header_bottom, row_height)
    _split_merged_cells(cells, columns)

    rows, scores = [], []
    for row_cells in cells:
        row, row_scores = {}, {}
        for col in columns:
            words = sorted(row_cells.get(col.title, []), key=lambda w: (round(w.cy / row_height), w.x1))
            row[col.title] = " ".join(w.text for w in words).strip()
            if words:
                row_scores[col.title] = min(w.score for w in words)
        rows.append(row)
        scores.append(row_scores)
    return Table(columns=columns, rows=rows, scores=scores)


def _header_columns(page: Page, serial_word: Word) -> List[Column]:
    """Collect header words around the serial header and group them into columns."""
    h = serial_word.height
    top, bottom = serial_word.cy - 1.4 * h, serial_word.cy + 1.4 * h
    # The header ends above the first item row ("1" under the serial header).
    first_serials = [
        w for w in page.words
        if w.cy > serial_word.cy
        and serial_word.x1 - h <= w.cx <= serial_word.x2 + h
        and _SERIAL_VALUE_RE.match(w.text.strip())
    ]
    if first_serials:
        first = min(first_serials, key=lambda w: w.cy)
        bottom = min(bottom, first.cy - 0.4 * first.height)
    header_words = [
        w for w in page.words
        if top <= w.cy <= bottom
        and re.search(r"[A-Za-z]", w.text)
        and not re.search(r"\d", w.text)
        and w.x2 > serial_word.x1 - h
    ]

    groups: List[List[Word]] = []
    for word in sorted(header_words, key=lambda w: w.x1):
        for group in groups:
            gx1 = min(w.x1 for w in group)
            gx2 = max(w.x2 for w in group)
            overlap = min(gx2, word.x2) - max(gx1, word.x1)
            if overlap > 0.3 * min(word.width, gx2 - gx1):
                group.append(word)
                break
        else:
            groups.append([word])

    columns = []
    for group in groups:
        group.sort(key=lambda w: (w.y1, w.x1))
        title = " ".join(w.text for w in group)
        columns.append(Column(title=title, x1=min(w.x1 for w in group), x2=max(w.x2 for w in group)))
    columns.sort(key=lambda c: c.x1)
    _dedupe_titles(columns)

    for i, col in enumerate(columns):
        col.left = (columns[i - 1].x2 + col.x1) / 2 if i > 0 else float("-inf")
        col.right = (col.x2 + columns[i + 1].x1) / 2 if i + 1 < len(columns) else float("inf")
    return columns


def _dedupe_titles(columns: List[Column]) -> None:
    seen: Dict[str, int] = {}
    for col in columns:
        key = col.title
        if key in seen:
            seen[key] += 1
            col.title = "{} ({})".format(key, seen[key])
        else:
            seen[key] = 1


def _row_anchors(page: Page, serial_col: Column, header_bottom: float) -> List[Word]:
    """Serial numbers (1, 2, 3, ...) under the serial header, in order."""
    found = []
    for w in page.words:
        if w.cy <= header_bottom or not (serial_col.left <= w.cx <= serial_col.right):
            continue
        match = _SERIAL_VALUE_RE.match(w.text.strip())
        if match:
            found.append((w, int(match.group(1))))
    found.sort(key=lambda item: item[0].cy)

    anchors: List[Word] = []
    last_number = 0
    for word, number in found:
        if anchors and number <= last_number:
            break
        if anchors and number > last_number + 3:
            break  # a jump this big is a footer value, not the next item
        anchors.append(word)
        last_number = number
    return anchors


def _assign_cells(
    page: Page,
    columns: List[Column],
    serial_col: Column,
    anchors: List[Word],
    header_bottom: float,
    row_height: float,
) -> List[Dict[str, List[Word]]]:
    cells: List[Dict[str, List[Word]]] = [{serial_col.title: [a]} for a in anchors]
    anchor_ids = {id(a) for a in anchors}
    expected = [a.cy for a in anchors]
    lowest = expected[-1] + 0.8 * row_height

    others = [c for c in columns if c is not serial_col]
    # Walk outwards from the serial column so skew is tracked step by step.
    right_side = [c for c in others if c.x1 > serial_col.x1]
    left_side = sorted((c for c in others if c.x1 <= serial_col.x1), key=lambda c: -c.x1)

    for side in (right_side, left_side):
        current = list(expected)
        for col in side:
            col_words = [
                w for w in page.words
                if id(w) not in anchor_ids
                and col.left <= w.cx < col.right
                and header_bottom < w.cy < lowest + (current[-1] - expected[-1])
            ]
            placed: Dict[int, List[Word]] = {}
            for w in col_words:
                idx = _row_for(w.cy, current, row_height)
                if idx is not None:
                    placed.setdefault(idx, []).append(w)
            for idx, words in placed.items():
                cells[idx].setdefault(col.title, []).extend(words)

            shifts = [min(w.cy for w in ws) - current[i] for i, ws in placed.items()]
            if shifts:
                avg = statistics.mean(shifts)
                for i in range(len(current)):
                    if i in placed:
                        current[i] = min(w.cy for w in placed[i])
                    else:
                        current[i] += avg
    return cells


def _row_for(y: float, expected: List[float], row_height: float) -> Optional[int]:
    """Index of the row whose band contains ``y`` (wrapped lines join the row above)."""
    if y < expected[0] - 0.5 * row_height or y > expected[-1] + 0.8 * row_height:
        return None
    for idx in range(len(expected) - 1, -1, -1):
        if y >= expected[idx] - 0.5 * row_height:
            return idx
    return None


def _split_merged_cells(cells: List[Dict[str, List[Word]]], columns: List[Column]) -> None:
    for row in cells:
        for col in columns:
            for word in list(row.get(col.title, [])):
                spanned = [
                    c for c in columns
                    if min(word.x2, c.right) - max(word.x1, c.left) > 0.25 * word.width
                ]
                if len(spanned) < 2:
                    continue
                if any(row.get(c.title) for c in spanned if c is not col):
                    continue  # neighbour already has its own value; leave as is
                parts = word.text.split()
                if len(parts) != len(spanned):
                    parts = re.findall(r"[A-Za-z][A-Za-z .&/-]*[A-Za-z.]|[A-Za-z]|[\d.,/-]+", word.text)
                    parts = [p.strip() for p in parts if p.strip()]
                if len(parts) != len(spanned):
                    continue
                row[col.title].remove(word)
                if not row[col.title]:
                    del row[col.title]
                for c, text in zip(spanned, parts):
                    row.setdefault(c.title, []).append(
                        Word(text, word.score, max(word.x1, c.left), word.y1, min(word.x2, c.right), word.y2)
                    )
