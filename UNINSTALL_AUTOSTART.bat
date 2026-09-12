@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=KEALinkWatch"

echo ============================================================
echo  KEA Link Watch -- remove "always running" mode
echo ============================================================
echo This removes the Windows Task Scheduler job named
echo "%TASK_NAME%" that INSTALL_AUTOSTART.bat created.
echo It does NOT delete this folder, your data, or your tokens --
echo it only stops the automatic every-15-minutes background runs.
echo ============================================================
echo.

schtasks /query /tn "%TASK_NAME%" >nul 2>nul
if errorlevel 1 (
    echo [OK] Nothing to remove -- "%TASK_NAME%" is not installed.
    echo.
    pause
    exit /b 0
)

schtasks /delete /tn "%TASK_NAME%" /f
if errorlevel 1 (
    echo.
    echo [PROBLEM] Could not remove the scheduled task. See the
    echo error above. You may need to run this as Administrator
    echo ^(right-click UNINSTALL_AUTOSTART.bat -^> "Run as administrator"^).
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Removed. The monitor will no longer run automatically.
echo.
echo  To run it again:
echo    - double-click START_MONITOR.bat for a visible run, or
echo    - double-click INSTALL_AUTOSTART.bat to re-enable
echo      the always-running background mode
echo ============================================================
echo.
pause
