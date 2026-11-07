"""Scan history: every scan is saved as one JSON file (with its CSV) in history/YYYY-MM/.

Used for the "Recent scans" list and to warn when the same invoice (same supplier and
invoice number) was scanned before.
"""

import copy
import json
import logging
import re
import threading
from collections import Counter
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
            # What the OCR read, kept unchanged so corrections can be compared with it later.
            data["original"] = copy.deepcopy({"header": invoice.header, "items": invoice.items})
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

    def update(self, scan_id: str, invoice: Invoice, csv_text: str) -> Optional[Dict]:
        """Save values the user corrected after the scan. Returns the original OCR values
        ({"header", "items", "supplier"}) so the caller can learn from the changes, or None
        when the scan is not in the history."""
        with self._lock:
            path = self._path(scan_id)
            if not _ID_RE.match(scan_id) or not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            original = data.get("original") or {"header": data.get("header") or {}, "items": data.get("items") or []}
            data["original"] = original
            original = dict(original, supplier_gstin=data.get("supplier_gstin", ""))
            data["header"] = invoice.header
            data["items"] = invoice.items
            data["csv"] = csv_text
            data["changes"] = changes(original, invoice.header, invoice.items)
            if data["changes"]:
                data["corrected"] = datetime.now().strftime("%d-%m-%Y %H:%M")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            return original

    def correction_stats(self, days: int = 90) -> Dict:
        """What users corrected, to see where the reading needs improving:
        {"scans", "corrected", "fields": {field: count}, "suppliers": [{name, scans, corrected,
        fields: {field: count}}], "rows_added", "rows_deleted"}."""
        cutoff = (datetime.now() - timedelta(days=max(1, days))).strftime("%Y%m%d")
        total, corrected = 0, 0
        fields: Counter = Counter()
        suppliers: Dict[str, Dict] = {}
        added = deleted = 0
        for path in self._files_newest_first():
            if path.name[:8] < cutoff:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            name = ((data.get("original") or data).get("header") or {}).get("supplier_name") or "(unknown supplier)"
            entry = suppliers.setdefault(name, {"name": name, "scans": 0, "corrected": 0, "fields": Counter()})
            total += 1
            entry["scans"] += 1
            scan_changes = data.get("changes") or []
            if not scan_changes:
                continue
            corrected += 1
            entry["corrected"] += 1
            for change in scan_changes:
                kind = change.get("kind")
                if kind == "row_added":
                    added += 1
                elif kind == "row_deleted":
                    deleted += 1
                else:
                    fields[change["field"]] += 1
                    entry["fields"][change["field"]] += 1
        ranked = sorted(suppliers.values(), key=lambda e: (-e["corrected"], -e["scans"]))
        for entry in ranked:
            entry["fields"] = dict(entry["fields"].most_common())
        return {"days": days, "scans": total, "corrected": corrected, "fields": dict(fields.most_common()),
                "rows_added": added, "rows_deleted": deleted, "suppliers": ranked}

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
                "supplier_gstin": data.get("supplier_gstin", ""),
                "items": len(data.get("items") or []),
                "amount": (data.get("total_check") or {}).get("items_total", ""),
                "warnings": len(data.get("warnings") or []),
                "files": data.get("files") or [],
                "corrected": data.get("corrected", ""),
            }
            if wanted:
                haystack = _key(" ".join([summary["supplier_name"], summary["invoice_number"],
                                          summary["supplier_gstin"]] + summary["files"]))
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
        """Earlier scans with the same invoice number from the same supplier. The supplier is
        compared by GSTIN when both scans have one (exact even when the name is read
        differently), otherwise by name."""
        number = _key(invoice.header.get("invoice_number", ""))
        supplier = _key(invoice.header.get("supplier_name", ""))
        gstin = invoice.supplier_gstin
        if not number or not (supplier or gstin):
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
            if _key(header.get("invoice_number", "")) != number:
                continue
            other_gstin = data.get("supplier_gstin") or ""
            same = (other_gstin == gstin) if (gstin and other_gstin) else (
                bool(supplier) and _key(header.get("supplier_name", "")) == supplier)
            if same:
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


def match_rows(original: List[Dict[str, str]], items: List[Dict[str, str]]) -> List[Optional[int]]:
    """For each corrected item, the index of the same item in the OCR result (by SKU, else by
    position when that row has no better match), or None for a row the user added."""
    by_sku: Dict[str, List[int]] = {}
    for index, item in enumerate(original):
        key = _key(item.get("sku", ""))
        if key:
            by_sku.setdefault(key, []).append(index)
    used = set()
    result: List[Optional[int]] = []
    for position, item in enumerate(items):
        found = None
        for index in by_sku.get(_key(item.get("sku", "")), []):
            if index not in used:
                found = index
                break
        if found is None and position < len(original) and position not in used:
            before = original[position]
            other = _key(before.get("sku", ""))
            alike = sum(1 for f in ("design_name", "quantity", "cost_price", "mrp", "amount")
                        if item.get(f) and item.get(f) == before.get(f))
            if alike >= 2 and (not other or other not in {_key(i.get("sku", "")) for i in items}):
                found = position  # same place and mostly the same values: the SKU was corrected
        if found is not None:
            used.add(found)
        result.append(found)
    return result


def changes(original: Dict, header: Dict[str, str], items: List[Dict[str, str]]) -> List[Dict]:
    """Differences between the OCR result and the corrected values."""
    found: List[Dict] = []
    for field, value in header.items():
        before = (original.get("header") or {}).get(field, "")
        if (value or "") != (before or ""):
            found.append({"row": 0, "field": field, "from": before, "to": value})
    old_items = original.get("items") or []
    matches = match_rows(old_items, items)
    for row, (item, index) in enumerate(zip(items, matches), start=1):
        if index is None:
            found.append({"row": row, "kind": "row_added"})
            continue
        for field, value in item.items():
            before = old_items[index].get(field, "")
            if (value or "") != (before or ""):
                found.append({"row": row, "field": field, "from": before, "to": value})
    for index in sorted(set(range(len(old_items))) - {i for i in matches if i is not None}):
        found.append({"row": index + 1, "kind": "row_deleted"})
    return found
