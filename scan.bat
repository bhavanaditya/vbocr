@echo off
rem Scan invoice files to CSV without the server.
rem   scan.bat invoice.jpg                     (CSV saved next to the image)
rem   scan.bat page1.jpg page2.jpg -o out.csv  (multi-page invoice)
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    echo Usage: scan.bat invoice.jpg [more pages...] [-o output.csv]
    exit /b 1
)
echo %* | findstr /c:"-o " >nul
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m vbocr scan %* -o "%~dpn1.csv"
) else (
    ".venv\Scripts\python.exe" -m vbocr scan %*
)
