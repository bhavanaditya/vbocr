@echo off
rem Stop starting the VB OCR server at Windows log-on (see autostart-on.bat).
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VB OCR server.vbs"
if exist "%VBS%" (
    del "%VBS%"
    echo VB OCR no longer starts at log-on. A server that is running now keeps running until log-off.
) else (
    echo VB OCR was not set to start at log-on.
)
pause
