"""Scan history: every scan is saved as one JSON file (with its CSV) in history/YYYY-MM/.

Used for the "Recent scans" list and to warn when the same invoice (same supplier and
invoice number) was scanned before.
"""

import json
import logging
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .models import Invoice

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^\d{8}-\d{6}-\d{3}(?:-[A-Za-z0-9-]{1,40})?$")


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


class History:
    def __init__(self, folder: Path, keep_days: int = 365, warn_duplicates: bool = True):
        self.folder = Path(folder)
        self.keep_days = int(keep_days or 0)
        self.warn_duplicates = warn_duplicates
        self._lock = threading.Lock()
        self._pruned = False

    # ---------------------------------------------------------------- saving

    def record(self, invoice: Invoice, csv_text: str, files: List[str]) -> None:
        """Warn about earlier scans of the same invoice, then save this scan."""
        with self._lock:
            if self.warn_duplicates:
                invoice.duplicates = self._find_duplicates(invoice)
                if invoice.duplicates:
                    first = invoice.duplicates[0]
                    invoice.warnings.append(
                        "Already scanned on {}{}: same supplier and invoice number {}. "
                        "Make sure it is not entered twice.".format(
                            first["scanned"],
                            " (and {} more time(s))".format(len(invoice.duplicates) - 1) if len(invoice.duplicates) > 1 else "",
                            invoice.header.get("invoice_number", ""),
                        )
                    )
            now = datetime.now()
            scan_id = now.strftime("%Y%m%d-%H%M%S-") + "{:03d}".format(now.microsecond // 1000)
            invoice_no = re.sub(r"[^A-Za-z0-9]+", "-", invoice.header.get("invoice_number", "")).strip("-")[:40]
            if invoice_no:
                scan_id += "-" + invoice_no
            invoice.scan_id = scan_id
            data = invoice.to_dict()
            data.update({
                "id": scan_id,
                "scanned": now.strftime("%d-%m-%Y %H:%M"),
                "scanned_iso": now.isoformat(timespec="seconds"),
                "files": [Path(f).name for f in files],
                "csv": csv_text,
            })
            path = self._path(scan_id)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            except OSError as error:
                log.warning("Could not save scan history %s: %s", path, error)
                invoice.scan_id = ""
            self._prune_once()

    def update(self, scan_id: str, invoice: Invoice, csv_text: str) -> bool:
        """Save values the user corrected after the scan."""
        with self._lock:
            path = self._path(scan_id)
            if not _ID_RE.match(scan_id) or not path.is_file():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
            data["header"] = invoice.header
            data["items"] = invoice.items
            data["csv"] = csv_text
            data["corrected"] = datetime.now().strftime("%d-%m-%Y %H:%M")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            return True

    # ---------------------------------------------------------------- reading

    def get(self, scan_id: str) -> Optional[Dict]:
        if not _ID_RE.match(scan_id or ""):
            return None
        path = self._path(scan_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def recent(self, limit: int = 50, query: str = "") -> List[Dict]:
        """Newest first. ``query`` filters on supplier, invoice number and file names."""
        wanted = _key(query)
        result = []
        for path in self._files_newest_first():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            header = data.get("header") or {}
            summary = {
                "id": data.get("id", path.stem),
                "scanned": data.get("scanned", ""),
                "supplier_name": header.get("supplier_name", ""),
                "invoice_number": header.get("invoice_number", ""),
                "invoice_date": header.get("invoice_date", ""),
                "items": len(data.get("items") or []),
                "amount": (data.get("total_check") or {}).get("items_total", ""),
                "warnings": len(data.get("warnings") or []),
                "files": data.get("files") or [],
                "corrected": data.get("corrected", ""),
            }
            if wanted:
                haystack = _key(" ".join([summary["supplier_name"], summary["invoice_number"]] + summary["files"]))
                if wanted not in haystack:
                    continue
            result.append(summary)
            if len(result) >= limit:
                break
        return result

    # ---------------------------------------------------------------- internals

    def _path(self, scan_id: str) -> Path:
        return self.folder / "{}-{}".format(scan_id[:4], scan_id[4:6]) / (scan_id + ".json")

    def _files_newest_first(self) -> List[Path]:
        if not self.folder.is_dir():
            return []
        return sorted(self.folder.glob("*/*.json"), key=lambda p: p.name, reverse=True)

    def _find_duplicates(self, invoice: Invoice) -> List[Dict[str, str]]:
        number = _key(invoice.header.get("invoice_number", ""))
        supplier = _key(invoice.header.get("supplier_name", ""))
        if not number or not supplier:
            return []
        found = []
        for path in self._files_newest_first():
            if number not in path.stem.lower().replace("-", ""):
                continue  # file name contains the invoice number: skip reading most files
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            header = data.get("header") or {}
            if _key(header.get("invoice_number", "")) == number and _key(header.get("supplier_name", "")) == supplier:
                found.append({"id": data.get("id", path.stem), "scanned": data.get("scanned", "")})
        return found

    def _prune_once(self) -> None:
        if self._pruned or self.keep_days <= 0:
            return
        self._pruned = True
        cutoff = (datetime.now() - timedelta(days=self.keep_days)).strftime("%Y%m%d")
        for path in self._files_newest_first():
            if path.name[:8] < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass
