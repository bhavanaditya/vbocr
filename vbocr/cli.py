"""Command line interface.

    python -m vbocr scan invoice.jpg -o invoice.csv              one invoice
    python -m vbocr scan page1.jpg page2.png -o invoice.csv      several pages of one invoice
    python -m vbocr scan --each bill1.jpg bill2.png bill3.pdf    every file is its own invoice
    python -m vbocr scan C:\\Invoices                            every image in the folder, each its own invoice
    python -m vbocr scan "C:\\Invoices\\*.png" --each -o C:\\Out  wildcards; CSVs written to C:\\Out
    python -m vbocr scan invoice.pdf --json
    python -m vbocr serve
    python -m vbocr setup
    python -m vbocr diagnostics                                  zip with logs and settings, to ask for help
"""

import argparse
import glob
import json
import logging
import os
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

    watch = sub.add_parser(
        "watch",
        help="Scan every invoice that appears in a folder (e.g. the scanner's output folder)",
        description="Each new file is scanned as a separate invoice. The CSV goes to the output "
        "folder, the file is moved to 'done' (or 'failed'). Stop with Ctrl+C.",
    )
    watch.add_argument("folder", help="Folder to watch")
    watch.add_argument("-o", "--output", help="Folder for the CSV files (default: <folder>\\csv)")

    add = sub.add_parser(
        "add-sample",
        help="Add your own invoice to the test bench (samples folder)",
        description="Copies the file(s) to samples\\<name>, scans them and saves the result as "
        "expected.csv. Then open expected.csv, correct every wrong value and save it.",
    )
    add.add_argument("files", nargs="+", help="Page(s) of one invoice")
    add.add_argument("--name", help="Name of the sample (default: the file name)")
    add.add_argument("--folder", help="Samples folder (default: samples in the VB OCR folder)")

    check = sub.add_parser("check-samples", help="Scan every sample again and list values that differ")
    check.add_argument("--folder", help="Samples folder (default: samples in the VB OCR folder)")

    sub.add_parser("setup", help="Download the OCR models now (needs internet once)")

    diag = sub.add_parser(
        "diagnostics",
        help="Save a zip with logs, settings (keys removed) and versions, to send when asking for help",
        description="Contains no invoices, scan history or item list.",
    )
    diag.add_argument("-o", "--output", help="Zip file or folder (default: the logs folder)")

    args = parser.parse_args(argv)
    _utf8_when_redirected()
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
            _save_mkldnn_off(settings.local_settings_path)
        print("OCR models are ready (test read {} lines).".format(lines), file=sys.stderr)
        return 0

    if args.command == "diagnostics":
        from . import diagnostics

        target = diagnostics.save(settings, args.output)
        print(str(target))
        print("Diagnostics saved. It holds logs, settings (access keys removed) and versions; "
              "no invoices.", file=sys.stderr)
        return 0

    if args.command == "serve":
        from .server import run

        _log_to_file_without_console()
        run(settings, host=args.host, port=args.port)
        return 0

    if args.command in ("add-sample", "check-samples"):
        from . import samples
        from .config import ROOT_DIR
        from .scanner import Scanner

        folder = Path(args.folder or os.environ.get("VBOCR_SAMPLES") or ROOT_DIR / "samples")
        scanner = Scanner(settings, record_history=False)
        if args.command == "check-samples":
            return 1 if samples.check_samples(scanner, folder, lambda line: print(line, file=sys.stderr)) else 0
        files, _, missing = expand_inputs(args.files)
        if missing or not files:
            print("File not found: {}".format(" ".join(missing or args.files)), file=sys.stderr)
            return 2
        target = samples.add_sample(scanner, files, folder, args.name)
        print("Sample saved in {}\nNow open {} in Excel, correct every wrong value and save it "
              "(keep the CSV format). Then check with:  python -m vbocr check-samples".format(
                  target, target / samples.EXPECTED), file=sys.stderr)
        return 0

    if args.command == "watch":
        from .scanner import Scanner
        from .watcher import FolderWatcher

        watcher = FolderWatcher(Scanner(settings), args.folder, args.output)
        print("Watching {} - new invoices are scanned automatically. Stop with Ctrl+C.".format(
            watcher.folder), file=sys.stderr)
        watcher.run_forever()
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
        return _write_result(scanner, scanner.scan(files), output, args.json)

    out_dir = Path(args.output) if args.output else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    worst = 0
    for index, name in enumerate(files, 1):
        print("[{}/{}] {}".format(index, len(files), name), file=sys.stderr)
        output = str(out_dir / Path(_default_output(name, args.json)).name) if out_dir else _default_output(name, args.json)
        try:
            invoices = scanner.scan_separate(name)
            if len(invoices) > 1:
                print("  {} invoices in this file".format(len(invoices)), file=sys.stderr)
            for part, invoice in enumerate(invoices, start=1):
                target = output if len(invoices) == 1 else _part_name(output, part)
                worst = max(worst, _write_result(scanner, invoice, target, args.json))
        except Exception as error:  # noqa: BLE001 - one bad file must not stop the batch
            failed += 1
            _report_error(error, name)
    print("Done: {} scanned, {} failed.".format(len(files) - failed, failed), file=sys.stderr)
    return 3 if failed else worst


def _part_name(output: str, part: int) -> str:
    path = Path(output)
    return str(path.with_name("{}_{}{}".format(path.stem, part, path.suffix)))


def _write_result(scanner, invoice, output: Optional[str], as_json: bool) -> int:
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
    """Save 'ocr: enable_mkldnn: false' in settings.local.yaml (this PC only), so the
    server does not hit the oneDNN bug (and the slow retry) on every start."""
    import yaml

    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("ocr", {})["enable_mkldnn"] = False
    text = "# Settings for this PC only. They override settings.yaml and are kept by update.bat.\n"
    text += yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
    print("This PC's CPU needs oneDNN switched off; saved enable_mkldnn: false in {}".format(path), file=sys.stderr)


def _utf8_when_redirected() -> None:
    """Output to a file or another program is UTF-8 (CSV with Hindi / accented text, file
    names). A real console window keeps showing Unicode as it does by itself."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _log_to_file_without_console() -> None:
    """pythonw.exe (server started hidden by the VB.NET app or at Windows start-up) has no
    console: write the output to logs/server.log so problems can be looked up."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_dir = ROOT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "server.log"
        if log_file.exists() and log_file.stat().st_size > 5 * 1024 * 1024:
            log_file.replace(log_dir / "server.old.log")
        stream = open(log_file, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)


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
