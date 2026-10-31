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
> "%VBS%" echo Set shell = CreateObject("WScript.Shell")
>> "%VBS%" echo shell.CurrentDirectory = "%~dp0"
>> "%VBS%" echo shell.Run """%~dp0.venv\Scripts\pythonw.exe"" -m vbocr serve", 0, False
echo VB OCR will start hidden when you log on to Windows.
echo Starting it now...
wscript "%VBS%"
echo Server log: %~dp0logs\server.log
pause
