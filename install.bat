@echo off
rem VB OCR - one-time installation for Windows
rem Needs Python 3.10 - 3.13 (64-bit, 3.11 recommended) and an internet connection.
setlocal
cd /d "%~dp0"

set "PY="
for %%V in (3.11 3.12 3.13 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; assert (3,10) <= sys.version_info[:2] <= (3,13)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo [ERROR] Python 3.10 - 3.13 ^(64-bit^) was not found.
    echo         Install Python 3.11 from https://www.python.org/downloads/windows/
    echo         and tick "Add python.exe to PATH" during setup.
    exit /b 1
)
echo Using %PY%

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv || goto :failed
)

echo Installing packages (this can take several minutes)...
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed

echo Downloading OCR models and testing them on this PC...
".venv\Scripts\python.exe" -m vbocr setup || goto :failed

echo.
echo ============================================================
echo  VB OCR is installed.
echo  Start the server:  start-server.bat
echo  Scan from command line:  scan.bat invoice.jpg   or   scan-folder.bat C:\Invoices
echo  Start it hidden at every Windows log-on:  autostart-on.bat
echo  Get a newer version later:  update.bat
echo  Your own settings go in config\settings.local.yaml
echo ============================================================
exit /b 0

:failed
echo.
echo [ERROR] Installation failed. See docs\TROUBLESHOOTING.md
exit /b 1
