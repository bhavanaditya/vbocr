"""High-level entry point: files in, Invoice / CSV out."""

from pathlib import Path
from typing import List, Optional

from .config import Settings
from .csv_output import invoice_to_csv
from .engine import OcrEngine
from .extractor import extract_invoice, split_pages
from .history import History
from .models import Invoice, Page


class Scanner:
    def __init__(self, settings: Optional[Settings] = None, record_history: bool = True):
        self.settings = settings or Settings()
        self.engine = OcrEngine(self.settings.ocr, self.settings.pdf, self.settings.photo)
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
        pages = self._read(paths)
        invoice = self._finish(pages, names or paths)
        groups = split_pages(pages, self.settings) if len(pages) > 1 else [pages]
        if len(groups) > 1:
            invoice.warnings.insert(0, (
                "These {} pages look like {} different invoices (different invoice numbers). "
                "Scan them as separate invoices if so.").format(len(pages), len(groups)))
        return invoice

    def scan_separate(self, path: str, name: Optional[str] = None) -> List[Invoice]:
        """Scan one file as its own invoice. A PDF / TIFF that holds several invoices (pages
        with different invoice numbers) gives one Invoice per invoice, in page order."""
        pages = self._read([path])
        groups = split_pages(pages, self.settings) if len(pages) > 1 else [pages]
        invoices = []
        for number, group in enumerate(groups, start=1):
            label = name or path
            if len(groups) > 1:
                label = "{} (invoice {} of {})".format(Path(label).name, number, len(groups))
            invoices.append(self._finish(group, [label]))
        return invoices

    def _read(self, paths: List[str]) -> List[Page]:
        pages: List[Page] = []
        for path in paths:
            pages.extend(self.engine.read(path))
        return pages

    def _finish(self, pages: List[Page], names: List[str]) -> Invoice:
        invoice = extract_invoice(pages, self.settings)
        invoice.source = "+".join(sorted({p.source for p in pages}))
        if self.history is not None:
            self.history.record(invoice, self.to_csv(invoice), names)
        return invoice

    def to_csv(self, invoice: Invoice) -> str:
        return invoice_to_csv(invoice, self.settings.output.get("include_total_row", True))
