@echo off
title WikiBot v3 - Local High-Speed Mode
color 0A
chcp 65001 >nul

echo.
echo  ============================================================
echo   WikiBot v3 - LOCAL HIGH-SPEED MODE
echo   5 threads x 1s = up to 300 edits/min
echo  ============================================================
echo.

cd /d "%~dp0"

REM ── Step 1: Find Python ──────────────────────────────────────
echo  [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found! Install Python from python.org
    pause
    exit /b 1
)
echo  [OK] Python found.

REM ── Step 2: Install missing packages ─────────────────────────
echo  [2/3] Installing required packages (fastapi, uvicorn, etc.)...
python -m pip install fastapi uvicorn pydantic requests python-dotenv urllib3 --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [WARN] pip install had issues, trying to continue anyway...
)
echo  [OK] Packages ready.

REM ── Step 3: Start the bot ─────────────────────────────────────
echo  [3/3] Starting WikiBot v3...
echo.
echo  Dashboard: http://localhost:8000
echo  Close this window to STOP the bot.
echo  ============================================================
echo.

python main.py

echo.
echo  [STOPPED] Bot has been stopped.
pause
