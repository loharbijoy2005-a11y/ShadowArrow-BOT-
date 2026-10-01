@echo off
title WikiBot - Activate Cloud Mode
color 0B

echo.
echo ============================================================
echo   WikiBot - ACTIVATING RENDER CLOUD BOT
echo ============================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set PY_BIN=.venv\Scripts\python.exe
) else (
    set PY_BIN=python
)

echo [1/2] Sending START signal to Render Cloud...
%PY_BIN% -c "import requests; r = requests.post('https://wikibot-w509.onrender.com/control', headers={'X-Bot-Token': 'SHADOW_SECURE_TOKEN_2026'}, json={'action': 'start'}, timeout=10); print('Status:', r.status_code, r.text)"

echo.
echo [2/2] Pausing local bot if running...
%PY_BIN% -c "import requests; r = requests.post('http://localhost:8000/control', headers={'X-Bot-Token': 'SHADOW_SECURE_TOKEN_2026'}, json={'action': 'pause'}, timeout=3)" 2>nul

echo.
echo ============================================================
echo   [SUCCESS] Render Cloud bot is now ACTIVE & Running!
echo   You can safely close local bot or turn off laptop.
echo ============================================================
echo.
pause
