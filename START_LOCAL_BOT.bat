@echo off
title WikiBot v3 - Local High-Speed Mode
color 0A
chcp 65001 >nul

echo.
echo  ============================================================
echo   WikiBot v3 - LOCAL AUTOMATION ENGINE
echo   Auto-Pauses Render Cloud and Runs Local Engine
echo  ============================================================
echo.

cd /d "%~dp0"

REM ── Step 1: Detect Python & Virtual Environment ───────────────
echo  [1/3] Detecting Python environment...

set "PYTHON_EXE=python"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo  [OK] Using virtualenv Python: "%~dp0.venv\Scripts\python.exe"
) else (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  [ERROR] Python is not installed or not in PATH!
        echo  Please install Python 3.10+ from https://www.python.org
        echo.
        pause
        exit /b 1
    )
    echo  [OK] Using system Python.
)

REM ── Step 2: Ensure Required Packages ─────────────────────────
echo  [2/3] Checking required Python packages...
"%PYTHON_EXE%" -m pip install fastapi uvicorn pydantic requests python-dotenv urllib3 --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [WARN] Pip install returned warnings/errors. Attempting to start bot anyway...
)
echo  [OK] Dependencies verified.

REM ── Step 3: Start Local Bot Engine ───────────────────────────
echo  [3/3] Starting WikiBot Local Engine...
echo.
echo  ============================================================
echo   LOCAL DASHBOARD: Double click LOCAL_DASHBOARD.html
echo   OR visit:        http://localhost:8000
echo   Render Cloud:    Auto-Paused while local runs
echo   To Stop:         Close this window OR run STOP_LOCAL_BOT.bat
echo  ============================================================
echo.

REM Open local dashboard in default browser after 2 seconds
timeout /t 2 /nobreak >nul
start "" "%~dp0LOCAL_DASHBOARD.html"

REM Execute bot backend
"%PYTHON_EXE%" main.py

if errorlevel 1 (
    echo.
    echo  ============================================================
    echo  [ERROR] Bot process exited with an error code!
    echo  Please inspect the log messages above to identify the issue.
    echo  ============================================================
    echo.
) else (
    echo.
    echo  [STOPPED] Bot process finished.
)

pause
