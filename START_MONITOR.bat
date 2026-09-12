@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=src"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ============================================================
    echo  PROBLEM: setup has not been run yet.
    echo.
    echo  Please double-click SETUP.bat first, then come back and
    echo  double-click START_MONITOR.bat again.
    echo ============================================================
    pause
    exit /b 1
)

echo ============================================================
echo  KEA Link Watch -- running
echo ============================================================
echo  What this window does:
echo    - Checks the KEA pages listed in config\link_watch_pages.txt
echo    - Every 15 minutes, automatically
echo    - Posts any newly-added link to your Telegram group
echo.
echo  Status:
echo    - The HEALTH Telegram group gets a check-mark after every
echo      run: a green check (OK) or a red cross (something failed).
echo    - The MAIN Telegram group only gets messages when there is
echo      something real to look at (a new result or a new link).
echo.
echo  To stop the monitor: simply close this window.
echo  While this window is open and running, the monitor is live.
echo ============================================================
echo.

"%VENV_PY%" scripts\preflight_check.py
if errorlevel 1 (
    pause
    exit /b 1
)
echo.

rem --- First run on this computer? Seed a starting point first. -------------
rem A fresh download (zip or git clone) normally has no memory of what's
rem already on the watched pages. Without this, the very first scan would
rem treat EVERY existing link as brand new and try to alert on all of it at
rem once. --baseline records what's out there right now WITHOUT sending any
rem alerts, so only links added AFTER this point ever reach Telegram.
rem This only happens once -- after this, data\cache exists and it's skipped.
rem (If data\cache came from `git pull`/a fresh clone of the shared repo, it
rem already has the team's baseline and this step is skipped entirely.)
if not exist "data\cache" (
    echo ============================================================
    echo  First run on this computer -- setting the starting point.
    echo  This checks the watched pages once and remembers what links
    echo  are already on them, WITHOUT sending anything to Telegram.
    echo  This is normal and only happens this one time. Please wait...
    echo ============================================================
    "%VENV_PY%" -m neet_pipeline.run_monitor --baseline
    if errorlevel 1 (
        echo.
        echo [PROBLEM] Could not set the starting point -- see the error
        echo above ^(usually no internet connection^). Fix that and
        echo double-click START_MONITOR.bat again -- it will retry this
        echo step before doing anything else.
        pause
        exit /b 1
    )
    echo [OK] Starting point set. Starting normal monitoring now...
    echo.
)

"%VENV_PY%" -m neet_pipeline.run_monitor --loop --interval 900

echo.
echo ============================================================
echo  The monitor has stopped ^(see any message above^).
echo  If this was not expected, please ask for help.
echo ============================================================
pause
