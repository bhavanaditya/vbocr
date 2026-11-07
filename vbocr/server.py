"""HTTP server used by the VB.NET application and the browser page.

    GET  /                  upload page for the browser
    GET  /health            {"status": "ok" | "loading", "version": ..., "key_required": bool}
    POST /scan              multipart form, field "files" (one or more). ?format=csv|json
                            ?mode=pages (default): all files are pages of ONE invoice
                            ?mode=each: every file is a separate invoice. Returns JSON
                            {"invoices": [...]} or, for format=csv, a ZIP with one CSV per file.
    POST /csv               JSON invoice (header + items, e.g. corrected in the browser) -> CSV.
                            With "scan_id", the corrections are also saved in the history.
    GET  /history           recent scans, newest first. ?limit=50&q=<supplier / invoice no>
    GET  /history.csv       the same list as CSV (for the VB.NET client)
    GET  /history/{id}      one saved scan (JSON)
    GET  /history/{id}.csv  its CSV
    GET  /stats             what users corrected (per supplier and column). ?days=90
    GET  /network           addresses other devices (a phone) can use to open this page
    POST /qr                {"text": ...} -> QR code (SVG), for opening the page on a phone
    GET  /diagnostics       zip with logs, settings (keys removed) and versions; no invoices

When server.api_key is set, every request except / and /health needs the key in the
"X-API-Key" header (or ?key=...).
"""

import csv
import hmac
import io
import json
import logging
import os
import re
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__, item_master
from .config import Settings
from .csv_output import HEADER_TITLES, ITEM_TITLES
from .engine import SUPPORTED_EXTENSIONS
from .models import HEADER_FIELDS, ITEM_FIELDS, Invoice
from .scanner import Scanner

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = SUPPORTED_EXTENSIONS
MAX_FILE_BYTES = 25 * 1024 * 1024

UPLOAD_PAGE = (Path(__file__).with_name("upload.html")).read_text(encoding="utf-8")

# CSV titles for the X-VBOCR-Unsure header (the VB.NET client works with CSV titles).
FIELD_TITLES = dict(zip(HEADER_FIELDS, HEADER_TITLES))
FIELD_TITLES.update(zip(ITEM_FIELDS, ITEM_TITLES[1:]))


def upload_name(upload) -> str:
    """The uploaded file's name, also when it has letters outside A-Z.

    Browsers send such names as UTF-8. .NET programs (HttpClient, PowerShell) send
    filename="=?utf-8?B?...?=" (an e-mail style encoding), and some clients add the standard
    filename*=UTF-8''%E0%A4%AC... The VB.NET client sends a plain A-Z name plus filename*."""
    from email.header import decode_header, make_header
    from urllib.parse import unquote

    name = upload.filename or ""
    disposition = ""
    try:
        disposition = upload.headers.get("content-disposition", "") or ""
    except AttributeError:
        pass
    star = re.search(r"filename\*\s*=\s*([\w-]+)'[^']*'([^;\s]+)", disposition, re.IGNORECASE)
    if star:
        try:
            name = unquote(star.group(2).strip('"'), encoding=star.group(1), errors="strict")
        except (LookupError, UnicodeDecodeError):
            pass
    elif "=?" in name and "?=" in name:
        try:
            name = str(make_header(decode_header(name)))
        except (ValueError, LookupError, UnicodeDecodeError):
            pass
    return re.split(r"[\\/]", name)[-1].strip()  # no folder part


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    state = {}
    api_key = str(settings.server.get("api_key") or "")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state["scanner"] = await run_in_threadpool(Scanner, settings)
        log.info("OCR engine ready")
        from .watcher import start_in_background

        stop_watch = start_in_background(state["scanner"], settings.data.get("watch") or {})
        yield
        if stop_watch is not None:
            stop_watch.set()

    app = FastAPI(title="VB OCR", version=__version__, lifespan=lifespan)

    def require_key(request: Request) -> None:
        if not api_key:
            return
        given = request.headers.get("x-api-key") or request.query_params.get("key") or ""
        if not hmac.compare_digest(given.encode("utf-8"), api_key.encode("utf-8")):
            raise HTTPException(401, "Access key missing or wrong. Ask the person who set up VB OCR for the key.")

    def scanner() -> Scanner:
        if "scanner" not in state:
            raise HTTPException(503, "VB OCR is still starting. Try again in a few seconds.")
        return state["scanner"]

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return UPLOAD_PAGE

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok" if "scanner" in state else "loading", "version": __version__,
                "key_required": bool(api_key), "check_updates": bool(settings.server.get("check_updates", True))}

    @app.post("/scan", dependencies=[Depends(require_key)])
    async def scan(
        files: List[UploadFile] = File(...),
        format: str = Query("csv", pattern="^(csv|json)$"),
        mode: str = Query("pages", pattern="^(pages|each)$"),
    ) -> Response:
        engine = scanner()
        saved = []
        try:
            for upload in files:
                name = upload_name(upload)
                suffix = Path(name).suffix.lower()
                if suffix not in ALLOWED_EXTENSIONS:
                    raise HTTPException(400, "Unsupported file type: {}".format(name))
                data = await upload.read()
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, "File too large: {}".format(name))
                handle, path = tempfile.mkstemp(suffix=suffix, prefix="vbocr_")
                with os.fdopen(handle, "wb") as out:
                    out.write(data)
                saved.append((name or Path(path).name, path))

            if mode == "each":
                return await run_in_threadpool(_scan_each, engine, saved, format)
            try:
                invoice = await run_in_threadpool(engine.scan, [p for _, p in saved], [n for n, _ in saved])
            except ValueError as error:  # unreadable / unsupported image
                raise HTTPException(400, _with_upload_names(str(error), saved))
        finally:
            for _, path in saved:
                try:
                    os.remove(path)
                except OSError:
                    pass

        csv_text = engine.to_csv(invoice)
        headers = result_headers(invoice)
        if format == "json":
            body = invoice.to_dict()
            body["csv"] = csv_text
            return JSONResponse(body, headers=headers)
        headers["Content-Disposition"] = 'attachment; filename="invoice.csv"'
        return Response(csv_text, media_type="text/csv; charset=utf-8", headers=headers)

    @app.post("/csv", dependencies=[Depends(require_key)])
    def make_csv(data: dict = Body(...)) -> Response:
        engine = scanner()
        invoice = Invoice.from_dict(data)
        csv_text = engine.to_csv(invoice)
        scan_id = str(data.get("scan_id") or "")
        headers = {}
        if scan_id and engine.history is not None:
            original = engine.history.update(scan_id, invoice, csv_text)
            master = settings.item_master
            if original is not None and master.get("learn", True) and master.get("learned_file"):
                learned_file = settings.resolve(master["learned_file"])
                try:
                    learned = item_master.learn(
                        learned_file,
                        # file it under what the next scan will read: the GSTIN, or the name as read
                        original.get("supplier_gstin") or (original.get("header") or {}).get("supplier_name", "")
                        or invoice.header.get("supplier_name", ""),
                        original.get("items") or [],
                        invoice.items,
                    )
                except OSError as error:
                    # Windows: the file is open in Excel. The corrections are saved; only the
                    # remembering of item values is skipped this time.
                    log.warning("Could not update %s (open in Excel?): %s", learned_file, error)
                    learned = 0
                    headers["X-VBOCR-Learn-Error"] = _latin1(
                        "{} is open in another program (Excel?). Corrections are saved; item values were "
                        "not remembered this time.".format(learned_file.name))
                headers["X-VBOCR-Learned"] = str(learned)
        return Response(csv_text, media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/network", dependencies=[Depends(require_key)])
    def network(request: Request) -> dict:
        host = str(settings.server.get("host", "127.0.0.1"))
        port = request.url.port or int(settings.server.get("port", 5000))
        shared = host not in ("127.0.0.1", "localhost", "::1")
        urls = ["http://{}:{}/".format(ip, port) for ip in lan_addresses()] if shared else []
        return {"shared": shared, "urls": urls, "port": port, "key_required": bool(api_key),
                "settings_file": str(settings.local_settings_path)}

    @app.post("/qr", dependencies=[Depends(require_key)])
    def qr(data: dict = Body(...)) -> Response:
        # POST, so a key in the text never ends up in the server log
        import segno

        text = str(data.get("text") or "")[:500]
        if not text:
            raise HTTPException(400, "text is empty")
        buffer = io.BytesIO()
        segno.make(text, error="m").save(buffer, kind="svg", scale=6, border=2, dark="#111827", light="#ffffff")
        return Response(buffer.getvalue(), media_type="image/svg+xml")

    @app.get("/diagnostics", dependencies=[Depends(require_key)])
    def diagnostics_zip() -> Response:
        from . import diagnostics

        return Response(diagnostics.build(settings), media_type="application/zip", headers={
            "Content-Disposition": 'attachment; filename="{}"'.format(diagnostics.file_name())})

    @app.get("/stats", dependencies=[Depends(require_key)])
    def stats(days: int = Query(90, ge=1, le=3650)) -> dict:
        engine = scanner()
        if engine.history is None:
            return {"enabled": False}
        result = engine.history.correction_stats(days)
        result["enabled"] = True
        return result

    @app.get("/history", dependencies=[Depends(require_key)])
    def history_list(limit: int = Query(50, ge=1, le=500), q: str = "") -> dict:
        engine = scanner()
        if engine.history is None:
            return {"enabled": False, "scans": []}
        return {"enabled": True, "scans": engine.history.recent(limit, q)}

    @app.get("/history.csv", dependencies=[Depends(require_key)])
    def history_list_csv(limit: int = Query(50, ge=1, le=500), q: str = "") -> Response:
        engine = scanner()
        scans = engine.history.recent(limit, q) if engine.history is not None else []
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        columns = ["id", "scanned", "supplier_name", "supplier_gstin", "invoice_number", "invoice_date",
                   "items", "amount", "warnings", "corrected"]
        writer.writerow(columns)
        for scan in scans:
            writer.writerow([scan.get(c, "") for c in columns])
        return Response(buffer.getvalue(), media_type="text/csv; charset=utf-8")

    @app.get("/history/{scan_id}.csv", dependencies=[Depends(require_key)])
    def history_csv(scan_id: str) -> Response:
        data = _history_item(scanner(), scan_id)
        name = (data.get("header", {}).get("invoice_number") or scan_id).replace('"', "").replace("/", "-")
        return Response(data.get("csv", ""), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="{}.csv"'.format(_latin1(name))})

    @app.get("/history/{scan_id}", dependencies=[Depends(require_key)])
    def history_get(scan_id: str) -> dict:
        return _history_item(scanner(), scan_id)

    return app


def result_headers(invoice: Invoice) -> dict:
    """Extra information for clients that ask for CSV (the VB.NET client)."""
    headers = {"X-VBOCR-Item-Count": str(len(invoice.items))}
    if invoice.warnings:
        headers["X-VBOCR-Warnings"] = _latin1(" | ".join(invoice.warnings))
    if invoice.unsure:
        # "Invoice Number;3:Quantity" = header value, and the quantity of item 3
        parts = []
        for entry in invoice.unsure:
            title = FIELD_TITLES.get(str(entry["field"]), str(entry["field"]))
            parts.append(title if not entry["row"] else "{}:{}".format(entry["row"], title))
        headers["X-VBOCR-Unsure"] = _latin1(";".join(parts))
    check = invoice.total_check or {}
    if check.get("status"):
        # status|items total|printed total|what the items should add up to (printed total
        # less the GST / freight / discount lines found)
        headers["X-VBOCR-Total-Check"] = "{}|{}|{}|{}".format(
            check.get("status"), check.get("items_total", ""), check.get("printed_total", ""),
            check.get("expected_items_total", ""))
    if check.get("note"):
        headers["X-VBOCR-Total-Note"] = _latin1(str(check["note"]))
    if invoice.scan_id:
        headers["X-VBOCR-Scan-Id"] = invoice.scan_id
    if invoice.duplicates:
        # earlier scans of the same invoice: "id|scanned;id|scanned"
        headers["X-VBOCR-Duplicates"] = ";".join(
            "{}|{}".format(d.get("id", ""), d.get("scanned", "")) for d in invoice.duplicates[:10])
    if invoice.source:
        headers["X-VBOCR-Source"] = invoice.source
    if invoice.supplier_gstin:
        headers["X-VBOCR-Supplier-GSTIN"] = invoice.supplier_gstin
    return headers


def lan_addresses() -> List[str]:
    """This PC's addresses on the office network (192.168.x.x, 10.x.x.x, 172.16-31.x.x)."""
    import ipaddress
    import socket

    found = []
    try:  # the address used to reach other networks; nothing is actually sent
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    result = []
    for address in found:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local and address not in result:
            result.append(address)
    return result


def _history_item(engine: Scanner, scan_id: str) -> dict:
    data = engine.history.get(scan_id) if engine.history is not None else None
    if data is None:
        raise HTTPException(404, "Scan not found: {}".format(scan_id))
    return data


def _latin1(text: str) -> str:
    """HTTP header values must be Latin-1."""
    return text.replace("₹", "Rs.").encode("latin-1", "replace").decode("latin-1")


def _scan_each(scanner: Scanner, saved: List[tuple], format: str) -> Response:
    """Scan every file as its own invoice. A failing file is reported, not fatal.
    A PDF that holds several invoices gives several entries (``part`` 1, 2, ... of ``parts``)."""
    results = []
    for name, path in saved:
        try:
            invoices = scanner.scan_separate(path, name)
        except Exception as error:  # noqa: BLE001
            log.exception("Scan failed for %s", name)
            message = _with_upload_names(str(error).strip(), [(name, path)])
            results.append({"file": name, "error": "{}: {}".format(type(error).__name__, message[:500])})
            continue
        for part, invoice in enumerate(invoices, start=1):
            entry = {"file": name}
            if len(invoices) > 1:
                entry.update({"part": part, "parts": len(invoices)})
            entry.update(invoice.to_dict())
            entry["csv"] = scanner.to_csv(invoice)
            results.append(entry)

    if format == "json":
        return JSONResponse({"invoices": results})

    buffer = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in results:
            stem = Path(entry["file"]).stem or "invoice"
            if entry.get("parts"):
                stem = "{}_{}".format(stem, entry["part"])
            name, n = stem, 1
            while name.lower() in used:
                n += 1
                name = "{}_{}".format(stem, n)
            used.add(name.lower())
            if "csv" in entry:
                archive.writestr(name + ".csv", "﻿" + entry["csv"])
            else:
                archive.writestr(name + ".ERROR.txt", entry["error"])
        summary = [{k: v for k, v in e.items() if k in ("file", "part", "parts", "error", "warnings")} for e in results]
        archive.writestr("summary.json", json.dumps(summary, indent=2))
    headers = {"Content-Disposition": 'attachment; filename="invoices.zip"'}
    return Response(buffer.getvalue(), media_type="application/zip", headers=headers)


def _with_upload_names(message: str, saved: List[tuple]) -> str:
    """Error messages mention the temporary file; show the uploaded file name instead."""
    for name, path in saved:
        message = message.replace("'{}'".format(path), "").replace(path, name).replace(Path(path).name, name)
    return message.replace(": :", ":").strip()


def run(settings: Settings, host: Optional[str] = None, port: Optional[int] = None) -> None:
    import uvicorn

    host = host or settings.server.get("host", "127.0.0.1")
    port = port or int(settings.server.get("port", 5000))
    if host not in ("127.0.0.1", "localhost", "::1") and not settings.server.get("api_key"):
        log.warning(
            "The server is open to other computers (host %s) without an access key. Anyone on the "
            "network can scan and see the scan history. Set server.api_key in %s.",
            host, settings.local_settings_path,
        )
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
