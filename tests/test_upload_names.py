"""Uploaded file names with letters outside A-Z (Hindi, accents), as browsers, .NET programs
and the VB.NET client send them. No OCR engine needed."""

import base64
from urllib.parse import quote

import pytest

pytest.importorskip("httpx")
from fastapi import FastAPI, File, UploadFile  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from vbocr.server import upload_name  # noqa: E402

NAME = "बिल नंबर 1 ü.jpg"


@pytest.fixture()
def client():
    app = FastAPI()

    @app.post("/name")
    async def name(files: UploadFile = File(...)) -> dict:
        return {"name": upload_name(files)}

    return TestClient(app)


def _post(client, disposition: bytes) -> str:
    body = (b"--b\r\nContent-Disposition: form-data; name=\"files\"; " + disposition
            + b"\r\nContent-Type: image/jpeg\r\n\r\nDATA\r\n--b--\r\n")
    response = client.post("/name", content=body, headers={"Content-Type": "multipart/form-data; boundary=b"})
    assert response.status_code == 200, response.text
    return response.json()["name"]


def test_browser_sends_utf8(client):
    assert _post(client, 'filename="{}"'.format(NAME).encode("utf-8")) == NAME


def test_dotnet_sends_encoded_word(client):
    # HttpClient / PowerShell Invoke-WebRequest -Form
    word = "=?utf-8?B?{}?=".format(base64.b64encode(NAME.encode("utf-8")).decode("ascii"))
    assert _post(client, 'filename="{}"'.format(word).encode("ascii")) == NAME


def test_vbnet_client_sends_plain_name_and_filename_star(client):
    header = "filename=\"___ ____ 1 _.jpg\"; filename*=UTF-8''{}".format(quote(NAME, safe=""))
    assert _post(client, header.encode("ascii")) == NAME


def test_plain_names_and_folders():
    class Upload:
        def __init__(self, filename, disposition=""):
            self.filename = filename
            self.headers = {"content-disposition": disposition}

    assert upload_name(Upload("bill.jpg")) == "bill.jpg"
    assert upload_name(Upload("C:\\Scans\\bill.png")) == "bill.png"
    assert upload_name(Upload("../../x.pdf")) == "x.pdf"
    assert upload_name(Upload(None)) == ""
    assert upload_name(Upload("=?broken")) == "=?broken"
    assert upload_name(Upload("x.jpg", "form-data; filename*=UTF-8''%ZZ")) in ("x.jpg", "%ZZ")
