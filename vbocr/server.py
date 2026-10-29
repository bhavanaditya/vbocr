"""HTTP server used by the VB.NET application.

    GET  /          simple upload page for testing in a browser
    GET  /health    {"status": "ok"}
    POST /scan      multipart form, field "files" (one or more). ?format=csv|json
"""

import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__
from .config import Settings
from .scanner import Scanner

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}
MAX_FILE_BYTES = 25 * 1024 * 1024

UPLOAD_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>VB OCR</title>
<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:640px;margin:40px auto;padding:0 16px}
button{padding:8px 16px}</style></head>
<body><h2>VB OCR - test upload</h2>
<p>Select the invoice image(s). Several files are treated as pages of one invoice.</p>
<form action="/scan" method="post" enctype="multipart/form-data"
 onsubmit="this.action='/scan?format='+this.format.value">
<p><input type="file" name="files" multiple accept="image/*,.pdf" required></p>
<p><label><input type="radio" name="format" value="csv" checked> CSV</label>
<label><input type="radio" name="format" value="json"> JSON</label></p>
<button type="submit">Scan</button></form></body></html>"""


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
                saved.append(path)

            invoice = await run_in_threadpool(scanner.scan, saved)
        finally:
            for path in saved:
                try:
                    os.remove(path)
                except OSError:
                    pass

        headers = {"X-VBOCR-Item-Count": str(len(invoice.items))}
        if invoice.warnings:
            headers["X-VBOCR-Warnings"] = " | ".join(invoice.warnings)
        if format == "json":
            return JSONResponse(invoice.to_dict(), headers=headers)
        headers["Content-Disposition"] = 'attachment; filename="invoice.csv"'
        return Response(scanner.to_csv(invoice), media_type="text/csv; charset=utf-8", headers=headers)

    return app


def run(settings: Settings, host: Optional[str] = None, port: Optional[int] = None) -> None:
    import uvicorn

    host = host or settings.server.get("host", "127.0.0.1")
    port = port or int(settings.server.get("port", 5000))
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
