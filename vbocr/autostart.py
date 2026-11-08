"""Start the server hidden at Windows log-on (used by autostart-on.bat).

A small VBScript in the user's Startup folder runs pythonw.exe (no window). It is written as
UTF-16 with a byte-order mark: Windows Script Host reads that correctly for any letters in the
path (C:\\Users\\Rāj\\vbocr), while a file written by "echo" in a .bat uses the console's code
page and garbles them, so nothing would start.
"""

import os
from pathlib import Path

from .config import ROOT_DIR

VBS_NAME = "VB OCR server.vbs"


def startup_folder() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def script_text(install_folder: Path) -> str:
    folder = str(install_folder).rstrip("\\/")
    pythonw = "{}\\.venv\\Scripts\\pythonw.exe".format(folder)
    quoted = lambda text: '"' + text.replace('"', '""') + '"'  # noqa: E731 - VBScript string
    return "\r\n".join([
        'Set shell = CreateObject("WScript.Shell")',
        "shell.CurrentDirectory = " + quoted(folder),
        "shell.Run " + quoted('"' + pythonw + '" -m vbocr serve') + ", 0, False",
        "",
    ])


def enable(install_folder: Path = ROOT_DIR, folder: Path = None) -> Path:
    folder = Path(folder or startup_folder())
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / VBS_NAME
    target.write_bytes(script_text(Path(install_folder)).encode("utf-16"))  # with BOM
    return target
