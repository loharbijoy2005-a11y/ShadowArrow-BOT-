@echo off
title WikiBot - Stopping...
color 0C

echo.
echo ============================================================
echo   [STOPPING] Killing all WikiBot local processes...
echo ============================================================
echo.

taskkill /f /im python.exe /fi "WINDOWTITLE eq WikiBot v3*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq WikiBot v3 - Local Mode" >nul 2>&1

echo [DONE] Local bot stopped. Render Cloud bot remains active.
echo.
pause
