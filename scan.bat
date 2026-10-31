@echo off
rem Scan invoices to CSV without the server. CSVs are saved next to the images.
rem   scan.bat invoice.jpg                        one invoice
rem   scan.bat page1.jpg page2.png                pages of ONE invoice (one CSV)
rem   scan.bat --each bill1.jpg bill2.png         every file is a separate invoice
rem   scan.bat C:\Invoices                        every image in the folder, one CSV each
rem   scan.bat "C:\Invoices\*.png" --each         wildcards
rem   scan.bat invoice.jpg -o C:\Output\bill.csv  choose where to save
rem You can also drag image files onto scan.bat in Explorer.
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    echo Usage: scan.bat invoice.jpg [more pages...] [--each] [-o output]
    echo        scan.bat C:\Invoices      ^(scan a whole folder^)
    goto :end
)
".venv\Scripts\python.exe" -m vbocr scan --next-to-input %*
:end
rem Keep the window open when started by drag-and-drop or double-click.
echo %cmdcmdline% | find /i "%~0" >nul && pause
