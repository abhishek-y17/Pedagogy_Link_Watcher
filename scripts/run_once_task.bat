@echo off
rem Called by Windows Task Scheduler (see INSTALL_AUTOSTART.bat). Not meant
rem to be double-clicked directly -- no window stays open, nothing pauses.
rem Runs one scan and appends its output to logs\autostart.log.

cd /d "%~dp0\.."
if not exist "logs" mkdir "logs"
set "PYTHONPATH=src"

if not exist ".venv\Scripts\python.exe" (
    echo %date% %time% -- ERROR: .venv not found. Run SETUP.bat first. >> "logs\autostart.log"
    exit /b 1
)

rem First run on this computer: seed a starting point before ever scanning
rem for real, same reasoning as START_MONITOR.bat -- otherwise the first
rem --once here would try to alert on every existing link at once. Only
rem runs when data\cache does not exist yet (i.e. once, ever).
if not exist "data\cache" (
    echo %date% %time% -- first run: setting starting point (--baseline) >> "logs\autostart.log"
    ".venv\Scripts\python.exe" -m neet_pipeline.run_monitor --baseline >> "logs\autostart.log" 2>&1
    if errorlevel 1 (
        echo %date% %time% -- ERROR: baseline failed, will retry next run >> "logs\autostart.log"
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m neet_pipeline.run_monitor --once >> "logs\autostart.log" 2>&1
