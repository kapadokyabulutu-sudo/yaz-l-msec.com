@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo YazilimSec veritabani baslatiliyor...
echo Tarayici birkac saniye icinde otomatik acilacak.
echo Bu pencereyi KAPATMAYIN. Durdurmak icin Ctrl+C kullanin.
echo.

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:3000/'"

where python >nul 2>nul
if %errorlevel%==0 (
    python server.py
) else (
    py -3 server.py
)

echo.
echo Sunucu durduruldu. Kapatmak icin bir tusa basin.
pause
