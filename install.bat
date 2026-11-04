@echo off
rem VB OCR - one-time installation for Windows
rem Needs an internet connection. Python 3.10 - 3.13 (64-bit) is used when installed;
rem otherwise Python 3.11 is downloaded from python.org (after asking).
setlocal
cd /d "%~dp0"

set "PY="
for %%V in (3.11 3.12 3.13 3.10) do (
    if not defined PY (
        py -%%V -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys, struct; assert (3,10) <= sys.version_info[:2] <= (3,13) and struct.calcsize('P') == 8" >nul 2>&1 && set "PY=python"
)
rem Installed earlier by this script (per user, not on PATH)
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python311\python.exe""
if not defined PY call :install_python
if not defined PY (
    echo.
    echo [ERROR] Python 3.10 - 3.13 ^(64-bit^) was not found.
    echo         Install Python 3.11 from https://www.python.org/downloads/windows/
    echo         and tick "Add python.exe to PATH" during setup. Then run install.bat again.
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

rem ---------------------------------------------------------------------------
rem Python is missing: offer to download the official 64-bit Python 3.11 from python.org
rem and install it for this Windows user only (no administrator rights needed).
rem Set VBOCR_YES=1 to answer yes without asking.
:install_python
set "PYVER=3.11.9"
set "PYEXE=%TEMP%\python-%PYVER%-amd64.exe"
echo.
echo Python 3.10 - 3.13 ^(64-bit^) was not found on this PC.
if not "%VBOCR_YES%"=="1" (
    choice /C YN /M "Download Python %PYVER% from python.org (about 25 MB) and install it for this user"
    if errorlevel 2 exit /b 0
)
echo Downloading https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%PYEXE%'"
if not exist "%PYEXE%" (
    echo [ERROR] Download failed. Check the internet connection.
    exit /b 0
)
rem Only run the installer when it is really signed by the Python Software Foundation.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = Get-AuthenticodeSignature '%PYEXE%'; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notlike '*Python Software Foundation*') { Write-Host ('Signature check failed: ' + $s.Status); exit 1 }"
if errorlevel 1 (
    echo [ERROR] The downloaded file is not a genuine Python installer. It was not run.
    del "%PYEXE%" >nul 2>&1
    exit /b 0
)
echo Installing Python %PYVER% for this user (takes a minute)...
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 InstallLauncherAllUsers=0 Include_test=0 Include_doc=0 Shortcuts=0
del "%PYEXE%" >nul 2>&1
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY="%LOCALAPPDATA%\Programs\Python\Python311\python.exe""
) else (
    echo [ERROR] Python setup did not finish.
)
exit /b 0
