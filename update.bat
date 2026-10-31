@echo off
rem Update VB OCR to the newest version. Your settings (config\settings.local.yaml),
rem item list (config\item_master.csv) and scan history (history\) are kept.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo VB OCR is not installed. Run install.bat first.
    pause
    exit /b 1
)

echo Stopping a running VB OCR server...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.CommandLine -like '*vbocr serve*' } | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }"

if exist ".git" (
    echo Downloading the newest version...
    git pull --ff-only || goto :gitfailed
) else (
    echo This folder was not installed with git.
    echo Download the newest version from https://github.com/bhavanaditya/vbocr
    echo and copy its files over this folder ^(keep the .venv, config\settings.local.yaml,
    echo config\item_master.csv and history folders^). Then run update.bat again.
    echo.
    echo Updating the Python packages of the current version only...
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
".venv\Scripts\python.exe" -m vbocr setup || goto :failed

echo.
echo ============================================================
echo  VB OCR is up to date.
echo  Start the server again: start-server.bat (or log off and on
echo  when autostart-on.bat is used).
echo ============================================================
pause
exit /b 0

:gitfailed
echo.
echo [ERROR] git pull failed. Files in this folder were changed by hand?
echo         Put your own settings in config\settings.local.yaml, not settings.yaml.
pause
exit /b 1

:failed
echo.
echo [ERROR] Update failed. See docs\TROUBLESHOOTING.md
pause
exit /b 1
