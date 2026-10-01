@echo off
title WikiBot v3 — Local High-Speed Mode
color 0A

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║       WikiBot v3 — LOCAL HIGH-SPEED MODE        ║
echo  ║   5 threads × 1s = up to 300 edits/min          ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  [INFO] Starting local bot engine...
echo  [INFO] Dashboard: http://localhost:8000
echo  [INFO] Close this window to STOP the bot.
echo.

cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Start the bot
python main.py

echo.
echo  [STOPPED] Bot has been stopped.
pause
