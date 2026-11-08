"""The log-on script written by autostart-on.bat. No OCR engine needed."""

from pathlib import Path

from vbocr import autostart


def test_script_for_a_path_with_spaces_and_non_english_letters(tmp_path):
    install = Path("C:\\Users\\Rāj Kumar\\VB OCR ü (1)")
    target = autostart.enable(install, tmp_path)
    data = target.read_bytes()
    assert data[:2] == b"\xff\xfe"                      # UTF-16 with BOM: read right by Windows Script Host
    text = data.decode("utf-16")
    assert text.splitlines() == [
        'Set shell = CreateObject("WScript.Shell")',
        'shell.CurrentDirectory = "C:\\Users\\Rāj Kumar\\VB OCR ü (1)"',
        'shell.Run """C:\\Users\\Rāj Kumar\\VB OCR ü (1)\\.venv\\Scripts\\pythonw.exe"" -m vbocr serve", 0, False',
    ]
    assert target.name == "VB OCR server.vbs"


def test_trailing_backslash_and_overwrite(tmp_path):
    autostart.enable(Path("C:\\vbocr\\"), tmp_path)
    target = autostart.enable(Path("C:\\vbocr"), tmp_path)
    assert 'shell.CurrentDirectory = "C:\\vbocr"' in target.read_bytes().decode("utf-16")
