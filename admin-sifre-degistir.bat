@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo YazilimSec admin sifresi guncelleniyor...
echo.

where python >nul 2>nul
if %errorlevel%==0 (
    python admin_sifre.py %*
) else (
    py -3 admin_sifre.py %*
)

echo.
echo Islem bitti. Kapatmak icin bir tusa basin.
pause
