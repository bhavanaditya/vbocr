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
    GET  /history/{id}      one saved scan (JSON)
    GET  /history/{id}.csv  its CSV

When server.api_key is set, every request except / and /health needs the key in the
"X-API-Key" header (or ?key=...).
"""

import hmac
import io
import json
import logging
import os
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__
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


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    state = {}
    api_key = str(settings.server.get("api_key") or "")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state["scanner"] = await run_in_threadpool(Scanner, settings)
        log.info("OCR engine ready")
        yield

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
                "key_required": bool(api_key)}

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
                suffix = Path(upload.filename or "").suffix.lower()
                if suffix not in ALLOWED_EXTENSIONS:
                    raise HTTPException(400, "Unsupported file type: {}".format(upload.filename))
                data = await upload.read()
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, "File too large: {}".format(upload.filename))
                handle, path = tempfile.mkstemp(suffix=suffix, prefix="vbocr_")
                with os.fdopen(handle, "wb") as out:
                    out.write(data)
                saved.append((upload.filename or Path(path).name, path))

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
        if scan_id and engine.history is not None:
            engine.history.update(scan_id, invoice, csv_text)
        return Response(csv_text, media_type="text/csv; charset=utf-8")

    @app.get("/history", dependencies=[Depends(require_key)])
    def history_list(limit: int = Query(50, ge=1, le=500), q: str = "") -> dict:
        engine = scanner()
        if engine.history is None:
            return {"enabled": False, "scans": []}
        return {"enabled": True, "scans": engine.history.recent(limit, q)}

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
        headers["X-VBOCR-Total-Check"] = "{}|{}|{}".format(
            check.get("status"), check.get("items_total", ""), check.get("printed_total", ""))
    if invoice.scan_id:
        headers["X-VBOCR-Scan-Id"] = invoice.scan_id
    if invoice.source:
        headers["X-VBOCR-Source"] = invoice.source
    return headers


def _history_item(engine: Scanner, scan_id: str) -> dict:
    data = engine.history.get(scan_id) if engine.history is not None else None
    if data is None:
        raise HTTPException(404, "Scan not found: {}".format(scan_id))
    return data


def _latin1(text: str) -> str:
    """HTTP header values must be Latin-1."""
    return text.replace("₹", "Rs.").encode("latin-1", "replace").decode("latin-1")


def _scan_each(scanner: Scanner, saved: List[tuple], format: str) -> Response:
    """Scan every file as its own invoice. A failing file is reported, not fatal."""
    results = []
    for name, path in saved:
        entry = {"file": name}
        try:
            invoice = scanner.scan([path], [name])
            entry.update(invoice.to_dict())
            entry["csv"] = scanner.to_csv(invoice)
        except Exception as error:  # noqa: BLE001
            log.exception("Scan failed for %s", name)
            message = _with_upload_names(str(error).strip(), [(name, path)])
            entry["error"] = "{}: {}".format(type(error).__name__, message[:500])
        results.append(entry)

    if format == "json":
        return JSONResponse({"invoices": results})

    buffer = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in results:
            stem = Path(entry["file"]).stem or "invoice"
            name, n = stem, 1
            while name.lower() in used:
                n += 1
                name = "{}_{}".format(stem, n)
            used.add(name.lower())
            if "csv" in entry:
                archive.writestr(name + ".csv", "﻿" + entry["csv"])
            else:
                archive.writestr(name + ".ERROR.txt", entry["error"])
        summary = [{k: v for k, v in e.items() if k in ("file", "error", "warnings")} for e in results]
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
