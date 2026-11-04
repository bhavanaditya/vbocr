@echo off
rem Scan every invoice that appears in a folder, e.g. the folder your scanner saves to.
rem   watch-folder.bat C:\Invoices\Inbox                CSV files go to C:\Invoices\Inbox\csv
rem   watch-folder.bat C:\Invoices\Inbox D:\Purchase\CSV
rem Scanned files are moved to Inbox\done, damaged ones to Inbox\failed. Close the window to stop.
rem To watch while the server runs instead, set watch: folder: in config\settings.local.yaml.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo VB OCR is not installed. Run install.bat first.
    pause
    exit /b 1
)
if "%~1"=="" (
    echo Usage: watch-folder.bat ^<folder to watch^> [folder for the CSV files]
    pause
    exit /b 1
)
if "%~2"=="" (
    ".venv\Scripts\python.exe" -m vbocr watch "%~1"
) else (
    ".venv\Scripts\python.exe" -m vbocr watch "%~1" -o "%~2"
)
pause
