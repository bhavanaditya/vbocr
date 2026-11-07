"""Diagnostics zip: everything needed to look into a problem, without invoice data.

    python -m vbocr diagnostics                 -> logs\\vbocr-diagnostics-<date>.zip
    diagnostics.bat                             the same, then opens the folder
    GET /diagnostics (browser: "Diagnostics" link) downloads it from the server

Contains: the log files, the settings (access keys, passwords and tokens removed),
suppliers.yaml, program and package versions, and the number of saved scans.
Never contains invoices, scan history, CSV files or the item master.
"""

import io
import json
import platform
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Dict, Optional

from . import __version__
from .config import LOCAL_SETTINGS, ROOT_DIR, Settings

LOG_DIR = ROOT_DIR / "logs"
MAX_LOG_BYTES = 2 * 1024 * 1024  # only the end of a large log
PACKAGES = ("paddlepaddle", "paddleocr", "paddlex", "numpy", "opencv-python", "opencv-contrib-python",
            "pypdfium2", "segno", "fastapi", "uvicorn", "PyYAML", "Pillow")
_SECRET = re.compile(r"^(\s*-?\s*[\w.-]*(?:key|password|passwd|token|secret)[\w.-]*\s*:\s*)(\S.*)$", re.IGNORECASE)
REMOVED = '"(removed)"'


def redact(text: str) -> str:
    """Settings text with the values of keys, passwords, tokens and secrets removed."""
    lines = []
    for line in text.splitlines():
        match = _SECRET.match(line)
        if match and match.group(2).strip() not in ('""', "''", "null", "~") and not match.group(2).startswith("#"):
            line = match.group(1) + REMOVED
        lines.append(line)
    return "\n".join(lines) + "\n"


def versions() -> Dict[str, str]:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python < 3.8
        return {}
    found = {}
    for name in PACKAGES:
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            continue
    return found


def summary(settings: Settings) -> Dict:
    history = settings.history
    folder = settings.resolve(history.get("folder") or "history")
    scans = sum(1 for _ in folder.glob("*/*.json")) if folder.is_dir() else 0
    return {
        "vbocr": __version__,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "python_bits": 64 if sys.maxsize > 2 ** 32 else 32,
        "python_path": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "install_folder": str(ROOT_DIR),
        "config_folder": str(settings.config_dir),
        "packages": versions(),
        "history": {"enabled": bool(history.get("enabled", True)), "saved_scans": scans},
        "server": {"host": settings.server.get("host"), "port": settings.server.get("port"),
                   "key_required": bool(settings.server.get("api_key"))},
        "ocr": dict(settings.ocr),
    }


def build(settings: Settings, log_dir: Optional[Path] = None) -> bytes:
    """The diagnostics zip as bytes."""
    log_dir = Path(log_dir or LOG_DIR)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.json", json.dumps(summary(settings), indent=2, default=str))
        for name in ("settings.yaml", LOCAL_SETTINGS, "suppliers.yaml"):
            path = settings.config_dir / name
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                archive.writestr("config/" + name, redact(text))
        if log_dir.is_dir():
            for path in sorted(log_dir.iterdir()):
                if not path.is_file() or path.suffix.lower() not in (".log", ".txt"):
                    continue
                data = path.read_bytes()
                if len(data) > MAX_LOG_BYTES:
                    data = b"... (start cut off)\n" + data[-MAX_LOG_BYTES:]
                archive.writestr("logs/" + path.name, data)
    return buffer.getvalue()


def file_name() -> str:
    return "vbocr-diagnostics-{}.zip".format(time.strftime("%Y%m%d-%H%M%S"))


def save(settings: Settings, output: Optional[str] = None) -> Path:
    target = Path(output) if output else LOG_DIR / file_name()
    if target.is_dir():
        target = target / file_name()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build(settings))
    return target
