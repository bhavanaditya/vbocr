@echo off
rem Scan every invoice image / PDF in a folder. One CSV is saved next to each file.
rem   scan-folder.bat C:\Invoices
rem   scan-folder.bat C:\Invoices -o C:\Output
rem You can also drag a folder onto scan-folder.bat in Explorer.
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    echo Usage: scan-folder.bat C:\Invoices [-o C:\Output]
    goto :end
)
".venv\Scripts\python.exe" -m vbocr scan --each %*
:end
echo %cmdcmdline% | find /i "%~0" >nul && pause
