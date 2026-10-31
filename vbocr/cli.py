"""Command line interface.

    python -m vbocr scan invoice.jpg -o invoice.csv              one invoice
    python -m vbocr scan page1.jpg page2.png -o invoice.csv      several pages of one invoice
    python -m vbocr scan --each bill1.jpg bill2.png bill3.pdf    every file is its own invoice
    python -m vbocr scan C:\\Invoices                            every image in the folder, each its own invoice
    python -m vbocr scan "C:\\Invoices\\*.png" --each -o C:\\Out  wildcards; CSVs written to C:\\Out
    python -m vbocr scan invoice.pdf --json
    python -m vbocr serve
    python -m vbocr setup
"""

import argparse
import glob
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import List, Optional, Tuple

from . import __version__

ROOT_DIR = Path(__file__).resolve().parent.parent
ERROR_LOG = ROOT_DIR / "logs" / "last-error.txt"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vbocr", description="Read invoice images into purchase-entry CSV.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="Folder that holds settings.yaml and suppliers.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser(
        "scan",
        help="Scan invoice image(s) or PDF.",
        description="Several files = pages of one invoice, unless --each is given. "
        "A folder scans every image/PDF in it, each as its own invoice. Wildcards like *.png work.",
    )
    scan.add_argument("files", nargs="+", help="Image / PDF files, folders or wildcards")
    scan.add_argument("--each", action="store_true", help="Treat every file as a separate invoice (one CSV each)")
    scan.add_argument(
        "-o", "--output",
        help="Output file. With --each or a folder: output folder (default: next to each image)",
    )
    scan.add_argument("--next-to-input", action="store_true", help="Save the CSV next to the (first) input file")
    scan.add_argument("--json", action="store_true", help="Output JSON instead of CSV")

    serve = sub.add_parser("serve", help="Start the HTTP server for the VB.NET application")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    sub.add_parser("setup", help="Download the OCR models now (needs internet once)")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        return _run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # noqa: BLE001 - show a short message, keep details in a file
        _report_error(error)
        return 3


def _run(args) -> int:
    from .config import Settings

    settings = Settings(Path(args.config) if args.config else None)

    if args.command == "setup":
        from .engine import OcrEngine

        engine = OcrEngine(settings.ocr)
        lines = engine.self_test()
        if engine.mkldnn_fallback:
            _save_mkldnn_off(settings.config_dir / "settings.yaml")
        print("OCR models are ready (test read {} lines).".format(lines), file=sys.stderr)
        return 0

    if args.command == "serve":
        from .server import run

        run(settings, host=args.host, port=args.port)
        return 0

    files, has_folder, missing = expand_inputs(args.files)
    for name in missing:
        print("File not found: {}".format(name), file=sys.stderr)
    if missing:
        return 2
    if not files:
        print("No invoice images or PDFs found in: {}".format(" ".join(args.files)), file=sys.stderr)
        return 2

    each = args.each or has_folder
    if has_folder and not args.each:
        print("Folder given: every file is scanned as a separate invoice.", file=sys.stderr)

    from .scanner import Scanner

    scanner = Scanner(settings)
    if not each:
        output = args.output or (_default_output(files[0], args.json) if args.next_to_input else None)
        return _scan_one(scanner, files, output, args.json)

    out_dir = Path(args.output) if args.output else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    worst = 0
    for index, name in enumerate(files, 1):
        print("[{}/{}] {}".format(index, len(files), name), file=sys.stderr)
        output = str(out_dir / Path(_default_output(name, args.json)).name) if out_dir else _default_output(name, args.json)
        try:
            worst = max(worst, _scan_one(scanner, [name], output, args.json))
        except Exception as error:  # noqa: BLE001 - one bad file must not stop the batch
            failed += 1
            _report_error(error, name)
    print("Done: {} scanned, {} failed.".format(len(files) - failed, failed), file=sys.stderr)
    return 3 if failed else worst


def _scan_one(scanner, files: List[str], output: Optional[str], as_json: bool) -> int:
    invoice = scanner.scan(files)
    result = json.dumps(invoice.to_dict(), indent=2) if as_json else scanner.to_csv(invoice)

    if output:
        # utf-8-sig so Excel opens the CSV with the right encoding
        with open(output, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(result)
        print("Saved {} ({} items)".format(output, len(invoice.items)), file=sys.stderr)
    else:
        sys.stdout.write(result)

    for warning in invoice.warnings:
        print("WARNING: {}".format(warning), file=sys.stderr)
    return 0 if invoice.items else 1


def expand_inputs(names: List[str]) -> Tuple[List[str], bool, List[str]]:
    """Expand folders and wildcards (Windows cmd does not expand *.png itself).

    Returns (files, a folder was given, names that matched nothing).
    """
    from .engine import SUPPORTED_EXTENSIONS

    files: List[str] = []
    missing: List[str] = []
    has_folder = False
    for name in names:
        path = Path(name)
        if path.is_dir():
            has_folder = True
            files.extend(
                str(p) for p in sorted(path.iterdir(), key=lambda p: p.name.lower())
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        elif path.is_file():
            files.append(str(path))
        elif glob.has_magic(name):
            matches = [m for m in sorted(glob.glob(name), key=str.lower)
                       if Path(m).is_file() and Path(m).suffix.lower() in SUPPORTED_EXTENSIONS]
            if matches:
                files.extend(matches)
            else:
                missing.append(name)
        else:
            missing.append(name)
    # Same file twice (e.g. folder + wildcard) would scan it twice.
    unique = list(dict.fromkeys(files))
    return unique, has_folder, missing


def _save_mkldnn_off(path: Path) -> None:
    """Write 'enable_mkldnn: false' under 'ocr:' so the server does not hit the oneDNN
    bug (and the slow retry) on every start. Edits the text to keep the comments."""
    import re

    text = path.read_text(encoding="utf-8")
    if re.search(r"^\s+enable_mkldnn\s*:", text, re.M):
        text = re.sub(r"^(\s+enable_mkldnn\s*:).*$", r"\1 false", text, count=1, flags=re.M)
    else:
        text = re.sub(
            r"^ocr:[^\n]*\n",
            lambda m: m.group(0) + "  enable_mkldnn: false   # set by setup: oneDNN fails on this PC's CPU\n",
            text, count=1, flags=re.M,
        )
    path.write_text(text, encoding="utf-8")
    print("This PC's CPU needs oneDNN switched off; saved enable_mkldnn: false in {}".format(path), file=sys.stderr)


def _default_output(name: str, as_json: bool) -> str:
    return str(Path(name).with_suffix(".json" if as_json else ".csv"))


def _report_error(error: Exception, name: str = "") -> None:
    """Short message on screen; full details in logs/last-error.txt for support."""
    details = traceback.format_exc()
    try:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        ERROR_LOG.write_text(details, encoding="utf-8")
        where = " Full details: {}".format(ERROR_LOG)
    except OSError:
        where = ""
        print(details, file=sys.stderr)
    message = str(error).strip().splitlines()
    print(
        "ERROR{}: {}: {}.{}".format(
            " in " + name if name else "", type(error).__name__, message[-1] if message else "", where
        ),
        file=sys.stderr,
    )
