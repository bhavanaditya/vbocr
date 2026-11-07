"""Diagnostics zip, phone link (QR) and network info. No OCR engine needed."""

import io
import json
import zipfile

import pytest

from vbocr import diagnostics
from vbocr.config import Settings

SETTINGS = """server:
  host: 0.0.0.0
  port: 5000
  api_key: ""
ocr:
  lang: en
"""
LOCAL = """server:
  api_key: very-secret-123   # keep private
  smtp_password: hunter2
ocr:
  enable_mkldnn: false
"""


def _settings(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text(SETTINGS, encoding="utf-8")
    (config / "settings.local.yaml").write_text(LOCAL, encoding="utf-8")
    (config / "suppliers.yaml").write_text("suppliers: []\n", encoding="utf-8")
    (config / "item_master.csv").write_text("sku,name\nA1,Secret item\n", encoding="utf-8")
    return Settings(config)


def test_redact_removes_keys_but_keeps_empty_values_and_other_settings():
    text = diagnostics.redact(LOCAL + 'other:\n  api_key: ""\n  token_count: 5\n')
    assert "very-secret-123" not in text and "hunter2" not in text
    assert 'api_key: "(removed)"' in text
    assert 'api_key: ""' in text            # an empty key shows that none is set
    assert "enable_mkldnn: false" in text
    assert 'token_count: "(removed)"' in text  # better too much removed than too little


def test_zip_has_logs_settings_and_versions_but_no_business_data(tmp_path):
    settings = _settings(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "server.log").write_text("started\n", encoding="utf-8")
    (logs / "last-error.txt").write_text("Traceback ...\n", encoding="utf-8")
    (logs / "old.zip").write_bytes(b"zip")
    (logs / "bill.csv").write_text("invoice", encoding="utf-8")
    data = diagnostics.build(settings, logs)
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = set(archive.namelist())
    assert names == {"summary.json", "config/settings.yaml", "config/settings.local.yaml",
                     "config/suppliers.yaml", "logs/server.log", "logs/last-error.txt"}
    local = archive.read("config/settings.local.yaml").decode("utf-8")
    assert "very-secret-123" not in local and "hunter2" not in local
    summary = json.loads(archive.read("summary.json"))
    assert summary["python"] and summary["vbocr"]
    assert summary["server"]["key_required"] is True
    assert "numpy" in summary["packages"]


def test_large_log_keeps_only_the_end(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "MAX_LOG_BYTES", 100)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "server.log").write_bytes(b"x" * 1000 + b"LAST LINE\n")  # bytes: same on Windows
    archive = zipfile.ZipFile(io.BytesIO(diagnostics.build(_settings(tmp_path), logs)))
    text = archive.read("logs/server.log").decode("utf-8")
    assert text.startswith("... (start cut off)") and text.endswith("LAST LINE\n") and len(text) < 200


def test_save_to_folder(tmp_path):
    target = diagnostics.save(_settings(tmp_path), str(tmp_path))
    assert target.parent == tmp_path and target.suffix == ".zip"
    assert zipfile.is_zipfile(target)


def test_server_endpoints_need_the_key(tmp_path):
    pytest.importorskip("httpx")
    pytest.importorskip("segno")
    from fastapi.testclient import TestClient

    from vbocr.server import create_app

    client = TestClient(create_app(_settings(tmp_path)))  # no "with": the OCR engine is not started
    assert client.get("/diagnostics").status_code == 401
    assert client.post("/qr", json={"text": "x"}).status_code == 401
    headers = {"X-API-Key": "very-secret-123"}

    response = client.get("/diagnostics", headers=headers)
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert b"very-secret-123" not in zipfile.ZipFile(io.BytesIO(response.content)).read("config/settings.local.yaml")

    response = client.post("/qr", json={"text": "http://192.168.1.20:5000/#key=abc"}, headers=headers)
    assert response.status_code == 200 and response.headers["content-type"].startswith("image/svg")
    assert b"<svg" in response.content
    assert client.post("/qr", json={"text": ""}, headers=headers).status_code == 400

    network = client.get("/network", headers=headers).json()
    assert network["shared"] is True and network["key_required"] is True
    assert all(url.startswith("http://") and url.endswith(":5000/") for url in network["urls"])
