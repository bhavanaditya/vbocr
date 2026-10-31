"""Plain data objects shared by the OCR, layout and output modules."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Word:
    """One line of text found by the OCR engine, with its bounding box."""

    text: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


@dataclass
class Page:
    words: List[Word]
    width: float
    height: float
    source: str = "ocr"  # "ocr" or "pdf-text" (read from the PDF's own text, no OCR)

    @property
    def full_text(self) -> str:
        return "\n".join(w.text for w in self.words)


@dataclass
class Column:
    """A table column, described by its header text and horizontal extent."""

    title: str
    x1: float
    x2: float
    left: float = 0.0   # boundary with the previous column
    right: float = 0.0  # boundary with the next column

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2


@dataclass
class Table:
    columns: List[Column]
    rows: List[Dict[str, str]]  # one dict per item row, keyed by column title
    # Lowest OCR confidence (0-1) of the text in each cell, same layout as ``rows``.
    scores: List[Dict[str, float]] = field(default_factory=list)


HEADER_FIELDS = [
    "date",
    "supplier_name",
    "po_date",
    "po_number",
    "lr_booking_date",
    "stock_received_date",
    "invoice_number",
    "invoice_date",
    "grn_number",
]

ITEM_FIELDS = [
    "sku",
    "article_id",
    "brand",
    "design_name",
    "size",
    "cup_size",
    "colour",
    "quantity",
    "cost_price",
    "mrp",
    "amount",
]


@dataclass
class Invoice:
    header: Dict[str, str] = field(default_factory=lambda: {k: "" for k in HEADER_FIELDS})
    items: List[Dict[str, str]] = field(default_factory=list)
    supplier_profile: str = ""
    warnings: List[str] = field(default_factory=list)
    # Values to double-check: {"row": 0, "field": "invoice_number"} for header values,
    # {"row": 3, "field": "quantity"} for item 3. Rows count from 1.
    unsure: List[Dict[str, object]] = field(default_factory=list)
    # Result of comparing the item amounts with the total printed on the invoice.
    total_check: Dict[str, object] = field(default_factory=dict)
    # Set by the scan history: where this scan was saved, and earlier scans of the same invoice.
    scan_id: str = ""
    duplicates: List[Dict[str, str]] = field(default_factory=list)
    source: str = ""  # "ocr", "pdf-text" or "ocr+pdf-text"

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "items": self.items,
            "supplier_profile": self.supplier_profile,
            "warnings": self.warnings,
            "unsure": self.unsure,
            "total_check": self.total_check,
            "scan_id": self.scan_id,
            "duplicates": self.duplicates,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Invoice":
        """Rebuild an invoice from to_dict() output (e.g. values corrected in the browser)."""
        invoice = cls()
        for key in HEADER_FIELDS:
            invoice.header[key] = str((data.get("header") or {}).get(key) or "")
        for item in data.get("items") or []:
            invoice.items.append({k: str((item or {}).get(k) or "") for k in ITEM_FIELDS})
        invoice.supplier_profile = str(data.get("supplier_profile") or "")
        return invoice
