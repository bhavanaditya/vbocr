@echo off
rem Start the VB OCR server hidden (no window) every time this user logs on to Windows.
rem Undo with autostart-off.bat.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo VB OCR is not installed. Run install.bat first.
    pause
    exit /b 1
)
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VB OCR server.vbs"
rem Written by Python (UTF-16), so any letters in the folder path work.
".venv\Scripts\python.exe" -m vbocr autostart
if errorlevel 1 (
    echo Could not set up the start at log-on.
    pause
    exit /b 1
)
echo VB OCR will start hidden when you log on to Windows.
echo Starting it now...
wscript "%VBS%"
echo Server log: %~dp0logs\server.log
pause
