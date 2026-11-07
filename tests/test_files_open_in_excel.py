"""Windows: Excel does not let other programs write a file it has open. A scan must not be
lost because its CSV is open, and saving corrections must work while the learned item list
is open. No OCR engine needed."""

import builtins

import pytest

from vbocr import cli


def _locked(names):
    real_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if "w" in mode and str(file).replace("\\", "/").split("/")[-1] in names:
            raise PermissionError(13, "Permission denied", str(file))
        return real_open(file, mode, *args, **kwargs)
    return fake_open


def test_csv_open_in_excel_is_saved_under_another_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "open", _locked({"bill.csv"}), raising=False)
    written = cli._save_text(str(tmp_path / "bill.csv"), "a,b\n")
    assert written.endswith("bill (2).csv")
    assert (tmp_path / "bill (2).csv").read_text(encoding="utf-8-sig") == "a,b\n"
    assert "open in another program" in capsys.readouterr().err


def test_existing_other_names_are_not_overwritten(tmp_path, monkeypatch):
    (tmp_path / "bill (2).csv").write_text("older result")
    monkeypatch.setattr(cli, "open", _locked({"bill.csv"}), raising=False)
    assert cli._save_text(str(tmp_path / "bill.csv"), "x").endswith("bill (3).csv")
    assert (tmp_path / "bill (2).csv").read_text() == "older result"


def test_normal_save(tmp_path):
    assert cli._save_text(str(tmp_path / "bill.csv"), "x") == str(tmp_path / "bill.csv")


def test_save_corrections_while_learned_file_is_open(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from vbocr import item_master, server
    from vbocr.config import Settings

    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text(
        "item_master:\n  learn: true\n  learned_file: {}\n".format((tmp_path / "learned.csv").as_posix()),
        encoding="utf-8")
    (config / "suppliers.yaml").write_text("suppliers: []\n", encoding="utf-8")
    saved = {}

    class FakeHistory:
        def update(self, scan_id, invoice, csv_text):
            saved["id"] = scan_id
            return {"supplier_gstin": "29AAGCS1234K1Z7", "header": {}, "items": [{"sku": "A1", "size": ""}]}

    class FakeScanner:
        def __init__(self, settings):
            self.settings = settings
            self.history = FakeHistory()

        def to_csv(self, invoice):
            return "csv"

    def locked_learn(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "learned.csv")

    monkeypatch.setattr(server, "Scanner", FakeScanner)
    monkeypatch.setattr(item_master, "learn", locked_learn)
    with TestClient(server.create_app(Settings(config))) as client:
        response = client.post("/csv", json={"scan_id": "20260101-x", "header": {}, "items": [{"sku": "A1", "size": "XL"}]})
    assert response.status_code == 200 and response.text == "csv"
    assert saved["id"] == "20260101-x"                      # corrections saved in the history
    assert response.headers["X-VBOCR-Learned"] == "0"
    assert "open in another program" in response.headers["X-VBOCR-Learn-Error"]
