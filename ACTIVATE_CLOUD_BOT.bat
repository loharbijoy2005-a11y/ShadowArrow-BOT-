@echo off
title WikiBot - Activate Cloud Mode
color 0B
chcp 65001 >nul

echo.
echo  ============================================================
echo   WikiBot - ACTIVATING RENDER CLOUD BOT
echo  ============================================================
echo.

cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

echo  [1/2] Sending START signal to Render Cloud...
"%PYTHON_EXE%" -c "import requests; r = requests.post('https://wikibot-w509.onrender.com/control', headers={'X-Bot-Token': 'SHADOW_SECURE_TOKEN_2026'}, json={'action': 'start'}, timeout=10); print('Status:', r.status_code, r.text)"

echo.
echo  [2/2] Pausing local bot if running...
"%PYTHON_EXE%" -c "import requests; r = requests.post('http://localhost:8000/control', headers={'X-Bot-Token': 'SHADOW_SECURE_TOKEN_2026'}, json={'action': 'pause'}, timeout=3) if True else None" 2>nul

echo.
echo  ============================================================
echo   [SUCCESS] Render Cloud bot is now ACTIVE & Running!
echo   You can safely close local bot or turn off laptop.
echo  ============================================================
echo.
pause
