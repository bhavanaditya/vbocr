"""High-level entry point: files in, Invoice / CSV out."""

from typing import List, Optional

from .config import Settings
from .csv_output import invoice_to_csv
from .engine import OcrEngine
from .extractor import extract_invoice
from .models import Invoice


class Scanner:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.engine = OcrEngine(self.settings.ocr)

    def scan(self, paths: List[str]) -> Invoice:
        """Scan one invoice. Several paths are treated as pages of the same invoice."""
        pages = []
        for path in paths:
            pages.extend(self.engine.read(path))
        return extract_invoice(pages, self.settings)

    def to_csv(self, invoice: Invoice) -> str:
        return invoice_to_csv(invoice, self.settings.output.get("include_total_row", True))
