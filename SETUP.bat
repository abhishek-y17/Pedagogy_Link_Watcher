@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  KEA Link Watch -- one-time setup
echo ============================================================
echo This window will:
echo   1. Check that Python is installed
echo   2. Create a private Python environment in this folder (.venv)
echo   3. Install everything the monitor needs
echo   4. Install the browser the monitor uses to read KEA pages
echo   5. Make sure config\.env exists (where your tokens go)
echo.
echo This only needs to be run ONCE. It can take a few minutes,
echo especially the browser download -- please be patient.
echo ============================================================
echo.

rem --- 1. Find Python ------------------------------------------------------
set "PYEXE="
python --version >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=python"
) else (
    py -3 --version >nul 2>nul
    if not errorlevel 1 set "PYEXE=py -3"
)

if "%PYEXE%"=="" (
    echo [PROBLEM] Python was not found on this computer.
    echo.
    echo Please install Python first:
    echo   1. Go to https://www.python.org/downloads/
    echo   2. Download and run the installer
    echo   3. IMPORTANT: on the first install screen, TICK the box
    echo      that says "Add python.exe to PATH"
    echo   4. After installing, close this window and double-click
    echo      SETUP.bat again
    echo.
    pause
    exit /b 1
)

echo [OK] Found Python:
%PYEXE% --version
echo.

rem --- 2. Create the virtual environment -----------------------------------
if exist ".venv\Scripts\python.exe" (
    echo [OK] Python environment already exists ^(.venv^) -- skipping creation.
) else (
    echo Creating a private Python environment in .venv ...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo [PROBLEM] Could not create the .venv folder. See the error above.
        pause
        exit /b 1
    )
    echo [OK] Environment created.
)
echo.

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [PROBLEM] Expected to find %VENV_PY% but it's not there.
    echo Setup did not complete correctly. Please ask for help.
    pause
    exit /b 1
)

rem --- 3. Install the required packages ------------------------------------
echo Installing required packages -- this can take a few minutes...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [PROBLEM] Could not upgrade pip. See the error above.
    pause
    exit /b 1
)

"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [PROBLEM] Package install failed. See the error above.
    echo A common cause is no internet connection. Try again once
    echo you're back online.
    pause
    exit /b 1
)
echo [OK] Packages installed.
echo.

rem --- 4. Install the browser used to read KEA pages ------------------------
echo Installing the browser component ^(Chromium^) the monitor uses
echo to read KEA's website -- this step downloads about 150 MB and
echo can take a few minutes on a slower connection...
"%VENV_PY%" -m playwright install chromium
if errorlevel 1 (
    echo [PROBLEM] Browser install failed. See the error above.
    echo A common cause is no internet connection. Try again once
    echo you're back online -- you can re-run SETUP.bat safely.
    pause
    exit /b 1
)
echo [OK] Browser installed.
echo.

rem --- 5. Make sure config\.env exists ---------------------------------------
if exist "config\.env" (
    echo [OK] config\.env already exists -- leaving it alone.
) else (
    if exist "config\.env.example" (
        copy /y "config\.env.example" "config\.env" >nul
        echo [ACTION NEEDED] Created config\.env from the template.
        echo.
        echo    ==========================================================
        echo     EDIT config\.env WITH YOUR TOKENS BEFORE STARTING.
        echo     Open the file "config\.env" in Notepad and fill in:
        echo       TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
        echo       HEALTH_BOT_TOKEN,   HEALTH_CHAT_ID
        echo    ==========================================================
        echo.
    ) else (
        echo [PROBLEM] config\.env.example is missing -- cannot create
        echo config\.env automatically. Please ask for help.
        pause
        exit /b 1
    )
)
echo.

echo ============================================================
echo  Setup complete!
echo.
echo  Next step: make sure config\.env has your real tokens in it,
echo  then double-click START_MONITOR.bat to run the monitor.
echo ============================================================
echo.
pause
