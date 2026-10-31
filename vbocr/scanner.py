"""High-level entry point: files in, Invoice / CSV out."""

from typing import List, Optional

from .config import Settings
from .csv_output import invoice_to_csv
from .engine import OcrEngine
from .extractor import extract_invoice
from .history import History
from .models import Invoice


class Scanner:
    def __init__(self, settings: Optional[Settings] = None, record_history: bool = True):
        self.settings = settings or Settings()
        self.engine = OcrEngine(self.settings.ocr, self.settings.pdf)
        options = self.settings.history
        self.history: Optional[History] = None
        if record_history and options.get("enabled", True):
            self.history = History(
                self.settings.resolve(options.get("folder") or "history"),
                keep_days=int(options.get("keep_days", 365) or 0),
                warn_duplicates=bool(options.get("warn_duplicates", True)),
            )

    def scan(self, paths: List[str], names: Optional[List[str]] = None) -> Invoice:
        """Scan one invoice. Several paths are treated as pages of the same invoice.

        ``names`` are the original file names (for the history) when ``paths`` are temp files.
        """
        pages = []
        for path in paths:
            pages.extend(self.engine.read(path))
        invoice = extract_invoice(pages, self.settings)
        sources = sorted({p.source for p in pages})
        invoice.source = "+".join(sources)
        if self.history is not None:
            self.history.record(invoice, self.to_csv(invoice), names or paths)
        return invoice

    def to_csv(self, invoice: Invoice) -> str:
        return invoice_to_csv(invoice, self.settings.output.get("include_total_row", True))
