@echo off
title WikiBot v3 - Local Mode
color 0A

echo.
echo ============================================================
echo   WikiBot v3 - LOCAL AUTOMATION ENGINE
echo   Auto-Pauses Render Cloud and Runs Local Engine
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/3] Detecting Python environment...
if exist ".venv\Scripts\python.exe" (
    set PY_BIN=.venv\Scripts\python.exe
    echo [OK] Using virtualenv Python.
) else (
    set PY_BIN=python
    echo [OK] Using system Python.
)

echo.
echo [2/3] Checking required Python packages...
%PY_BIN% -m pip install fastapi uvicorn pydantic requests python-dotenv urllib3 --quiet --disable-pip-version-check
echo [OK] Dependencies verified.

echo.
echo [3/3] Starting WikiBot Local Engine...
echo.
echo ============================================================
echo   LOCAL DASHBOARD: Double click LOCAL_DASHBOARD.html
echo   OR visit:        http://localhost:8000
echo   Render Cloud:    Auto-Paused while local runs
echo   To Stop:         Close this window OR run STOP_LOCAL_BOT.bat
echo ============================================================
echo.

timeout /t 2 /nobreak >nul
start "" "LOCAL_DASHBOARD.html"

%PY_BIN% main.py

if errorlevel 1 (
    echo.
    echo ============================================================
    echo [ERROR] Bot process exited with an error!
    echo ============================================================
    echo.
) else (
    echo.
    echo [STOPPED] Bot process finished.
)

pause
