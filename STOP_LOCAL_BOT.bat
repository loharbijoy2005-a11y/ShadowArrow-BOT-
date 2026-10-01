@echo off
title WikiBot — Stopping...
color 0C

echo.
echo  [STOPPING] Killing all WikiBot local processes...
echo.

taskkill /f /im python.exe /fi "WINDOWTITLE eq WikiBot v3*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq WikiBot v3 — Local High-Speed Mode" >nul 2>&1

echo  [DONE] Local bot stopped. Render will continue running in background.
echo.
pause
