@echo off
rem Save a diagnostics zip (logs, settings with access keys removed, versions) in the logs folder
rem and show it in Explorer. Send that zip when asking for help. It holds no invoices.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo VB OCR is not installed. Run install.bat first.
    pause
    exit /b 1
)
set "ZIPFILE="
for /f "usebackq delims=" %%F in (`".venv\Scripts\python.exe" -m vbocr diagnostics`) do set "ZIPFILE=%%F"
if not defined ZIPFILE (
    echo Could not save the diagnostics zip. See the message above.
    pause
    exit /b 1
)
echo Saved: %ZIPFILE%
explorer /select,"%ZIPFILE%"
pause
