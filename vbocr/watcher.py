"""Watch a folder and scan every invoice that appears in it.

Typical use: the office scanner (or a phone app, or WhatsApp Desktop downloads) saves into
C:\\Invoices\\Inbox. Every new file is scanned as a separate invoice:

    Inbox\\bill.jpg  ->  Inbox\\csv\\bill.csv      (CSV for the purchase entry)
                    ->  Inbox\\done\\bill.jpg     (moved, so it is not scanned twice)
    damaged file    ->  Inbox\\failed\\x.jpg + x.jpg.error.txt

The scans also appear under "Recent scans" in the browser. A file is only taken once its size
has stopped changing, so files still being copied or scanned are not read half-written.
"""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .engine import SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)


class FolderWatcher:
    def __init__(self, scanner, folder: str, output: Optional[str] = None, interval: float = 3.0):
        self.scanner = scanner
        self.folder = Path(folder).resolve()
        self.output = Path(output).resolve() if output else self.folder / "csv"
        self.done = self.folder / "done"
        self.failed = self.folder / "failed"
        self.interval = max(0.5, float(interval))
        self._sizes: Dict[Path, Tuple[int, float]] = {}

    def run_forever(self, stop: Optional[threading.Event] = None) -> None:
        stop = stop or threading.Event()
        if not self.folder.is_dir():
            log.error("Watch folder not found: %s", self.folder)
            return
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:  # noqa: BLE001 - keep watching
                log.exception("Watch folder %s", self.folder)
            stop.wait(self.interval)

    def run_once(self) -> List[str]:
        """Scan the files that are ready. Returns the CSV files written."""
        written: List[str] = []
        for path in self._ready_files():
            written.extend(self._process(path))
        return written

    def _ready_files(self) -> List[Path]:
        ready = []
        seen = set()
        for path in sorted(self.folder.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS or path.name.startswith(("~", ".")):
                continue
            seen.add(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            state = (stat.st_size, stat.st_mtime)
            if stat.st_size > 0 and self._sizes.get(path) == state:
                ready.append(path)
            self._sizes[path] = state
        for gone in set(self._sizes) - seen:
            del self._sizes[gone]
        return ready

    def _process(self, path: Path) -> List[str]:
        self._sizes.pop(path, None)
        log.info("Watch folder: scanning %s", path.name)
        try:
            invoices = self.scanner.scan_separate(str(path), path.name)
        except Exception as error:  # noqa: BLE001
            log.warning("Watch folder: %s failed: %s", path.name, error)
            target = _move(path, self.failed)
            if target is not None:
                target.with_name(target.name + ".error.txt").write_text(
                    "{}: {}\n".format(type(error).__name__, error), encoding="utf-8")
            return []

        self.output.mkdir(parents=True, exist_ok=True)
        written = []
        for part, invoice in enumerate(invoices, start=1):
            stem = path.stem if len(invoices) == 1 else "{}_{}".format(path.stem, part)
            csv_path = _free_name(self.output / (stem + ".csv"))
            # utf-8-sig so Excel opens the CSV with the right encoding
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(self.scanner.to_csv(invoice))
            written.append(str(csv_path))
            log.info("Watch folder: %s -> %s (%d items%s)", path.name, csv_path.name, len(invoice.items),
                     ", {} warning(s)".format(len(invoice.warnings)) if invoice.warnings else "")
        _move(path, self.done)
        return written


def _free_name(path: Path) -> Path:
    """bill.csv, bill (2).csv, ... so an existing file is never overwritten."""
    candidate, n = path, 1
    while candidate.exists():
        n += 1
        candidate = path.with_name("{} ({}){}".format(path.stem, n, path.suffix))
    return candidate


def _move(path: Path, folder: Path) -> Optional[Path]:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target = _free_name(folder / path.name)
        shutil.move(str(path), str(target))
        return target
    except OSError as error:
        log.warning("Could not move %s to %s: %s", path, folder, error)
        return None


def start_in_background(scanner, options: dict) -> Optional[threading.Event]:
    """Used by the server when settings.yaml has watch.folder. Returns the stop event."""
    folder = str(options.get("folder") or "").strip()
    if not folder:
        return None
    watcher = FolderWatcher(scanner, str(scanner.settings.resolve(folder)),
                            str(scanner.settings.resolve(options["output"])) if options.get("output") else None,
                            float(options.get("interval_seconds", 3)))
    stop = threading.Event()
    thread = threading.Thread(target=watcher.run_forever, args=(stop,), name="vbocr-watch", daemon=True)
    thread.start()
    log.info("Watching %s for new invoices (CSV files go to %s)", watcher.folder, watcher.output)
    return stop
