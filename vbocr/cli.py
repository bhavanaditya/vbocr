"""Command line interface.

    python -m vbocr scan invoice.jpg -o invoice.csv
    python -m vbocr scan page1.jpg page2.jpg -o invoice.csv
    python -m vbocr scan invoice.pdf --json
    python -m vbocr serve
    python -m vbocr setup
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vbocr", description="Read invoice images into purchase-entry CSV.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="Folder that holds settings.yaml and suppliers.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan invoice image(s) or PDF. Several files = pages of one invoice.")
    scan.add_argument("files", nargs="+")
    scan.add_argument("-o", "--output", help="Write the result to this file instead of the screen")
    scan.add_argument("--json", action="store_true", help="Output JSON instead of CSV")

    serve = sub.add_parser("serve", help="Start the HTTP server for the VB.NET application")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    sub.add_parser("setup", help="Download the OCR models now (needs internet once)")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from .config import Settings

    settings = Settings(Path(args.config) if args.config else None)

    if args.command == "setup":
        from .engine import OcrEngine

        OcrEngine(settings.ocr)
        print("OCR models are ready.", file=sys.stderr)
        return 0

    if args.command == "serve":
        from .server import run

        run(settings, host=args.host, port=args.port)
        return 0

    for name in args.files:
        if not Path(name).is_file():
            print("File not found: {}".format(name), file=sys.stderr)
            return 2

    from .scanner import Scanner

    scanner = Scanner(settings)
    invoice = scanner.scan(args.files)
    result = json.dumps(invoice.to_dict(), indent=2) if args.json else scanner.to_csv(invoice)

    if args.output:
        # utf-8-sig so Excel opens the CSV with the right encoding
        with open(args.output, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(result)
        print("Saved {}".format(args.output), file=sys.stderr)
    else:
        sys.stdout.write(result)

    for warning in invoice.warnings:
        print("WARNING: {}".format(warning), file=sys.stderr)
    return 0 if invoice.items else 1
