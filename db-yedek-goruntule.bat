@echo off
chcp 65001 >nul
cd /d "%~dp0"

python db_yedek_goruntule.py %*
echo.
pause
