@echo off
rem Start the VB OCR server (keep this window open while scanning).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo VB OCR is not installed. Run install.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m vbocr serve %*
pause
