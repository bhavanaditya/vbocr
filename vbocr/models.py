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

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "items": self.items,
            "supplier_profile": self.supplier_profile,
            "warnings": self.warnings,
        }
