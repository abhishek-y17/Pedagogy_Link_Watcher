@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=KEALinkWatch"

echo ============================================================
echo  KEA Link Watch -- install "always running" mode
echo ============================================================
echo This registers a Windows Task Scheduler job that:
echo   - runs one check every 1 minute
echo   - starts automatically when this user logs in
echo   - keeps running with NO window open
echo   - keeps working after this computer restarts, once someone
echo     logs back in (this office PC stays on 24/7, so that's
echo     normally within moments)
echo.
echo This is the "set and forget" way to run the monitor. If you'd
echo rather watch it run in a window instead, use START_MONITOR.bat
echo and don't run this.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [PROBLEM] Setup has not been run yet.
    echo Please double-click SETUP.bat first, then run this again.
    echo.
    pause
    exit /b 1
)

echo Checking config\.env is filled in...
".venv\Scripts\python.exe" scripts\preflight_check.py
if errorlevel 1 (
    echo.
    echo Fix the above, then run INSTALL_AUTOSTART.bat again.
    pause
    exit /b 1
)
echo.

echo Registering the scheduled task "%TASK_NAME%" ...
schtasks /create /tn "%TASK_NAME%" ^
    /tr "\"%~dp0scripts\run_once_task.bat\"" ^
    /sc MINUTE /mo 1 /rl LIMITED /f
if errorlevel 1 (
    echo.
    echo [PROBLEM] Could not register the scheduled task. See the
    echo error above. You may need to run this as Administrator
    echo ^(right-click INSTALL_AUTOSTART.bat -^> "Run as administrator"^).
    pause
    exit /b 1
)

echo.
echo Running it once right now, to prove it works...
schtasks /run /tn "%TASK_NAME%"
echo.

echo ============================================================
echo  Installed!
echo.
echo  What was registered:
echo    Task name : %TASK_NAME%
echo    Runs      : every 1 minute, as this Windows user
echo    Where     : %~dp0
echo    Log file  : %~dp0logs\autostart.log
echo.
echo  To CHECK it's running:
echo    - Open the Start Menu, search for "Task Scheduler"
echo    - Look for "%TASK_NAME%" in the Task Scheduler Library
echo    - Or check the HEALTH Telegram group for the next
echo      check-mark message ^(within ~1 minute^)
echo    - Or open logs\autostart.log in Notepad
echo.
echo  To STOP it: double-click UNINSTALL_AUTOSTART.bat
echo ============================================================
echo.
pause
