"""HTTP server used by the VB.NET application.

    GET  /          simple upload page for testing in a browser
    GET  /health    {"status": "ok"}
    POST /scan      multipart form, field "files" (one or more). ?format=csv|json
                    ?mode=pages (default): all files are pages of ONE invoice
                    ?mode=each: every file is a separate invoice. Returns JSON
                    {"invoices": [...]} or, for format=csv, a ZIP with one CSV per file.
"""

import io
import json
import logging
import os
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__
from .config import Settings
from .engine import SUPPORTED_EXTENSIONS
from .scanner import Scanner

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = SUPPORTED_EXTENSIONS
MAX_FILE_BYTES = 25 * 1024 * 1024

UPLOAD_PAGE = (Path(__file__).with_name("upload.html")).read_text(encoding="utf-8")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    state = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state["scanner"] = await run_in_threadpool(Scanner, settings)
        log.info("OCR engine ready")
        yield

    app = FastAPI(title="VB OCR", version=__version__, lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return UPLOAD_PAGE

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok" if "scanner" in state else "loading", "version": __version__}

    @app.post("/scan")
    async def scan(
        files: List[UploadFile] = File(...),
        format: str = Query("csv", pattern="^(csv|json)$"),
        mode: str = Query("pages", pattern="^(pages|each)$"),
    ) -> Response:
        scanner: Scanner = state["scanner"]
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
                return await run_in_threadpool(_scan_each, scanner, saved, format)
            try:
                invoice = await run_in_threadpool(scanner.scan, [path for _, path in saved])
            except ValueError as error:  # unreadable / unsupported image
                raise HTTPException(400, _with_upload_names(str(error), saved))
        finally:
            for _, path in saved:
                try:
                    os.remove(path)
                except OSError:
                    pass

        headers = {"X-VBOCR-Item-Count": str(len(invoice.items))}
        if invoice.warnings:
            headers["X-VBOCR-Warnings"] = " | ".join(invoice.warnings)
        if format == "json":
            body = invoice.to_dict()
            body["csv"] = scanner.to_csv(invoice)
            return JSONResponse(body, headers=headers)
        headers["Content-Disposition"] = 'attachment; filename="invoice.csv"'
        return Response(scanner.to_csv(invoice), media_type="text/csv; charset=utf-8", headers=headers)

    return app


def _scan_each(scanner: Scanner, saved: List[tuple], format: str) -> Response:
    """Scan every file as its own invoice. A failing file is reported, not fatal."""
    results = []
    for name, path in saved:
        entry = {"file": name}
        try:
            invoice = scanner.scan([path])
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
                archive.writestr(name + ".csv", "\ufeff" + entry["csv"])
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
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
