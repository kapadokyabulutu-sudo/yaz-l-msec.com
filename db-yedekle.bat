@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "data\yazilimsec.db" (
    echo Veritabani bulunamadi: data\yazilimsec.db
    echo Once siteyi "YazilimSec Veritabani" kisayoluyla acip en az bir kayit yapin.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$d = Get-Date -Format 'yyyyMMdd-HHmmss'; $src = Join-Path (Get-Location) 'data\yazilimsec.db'; $dst = Join-Path (Get-Location) ('data\yazilimsec-' + $d + '.db'); Copy-Item $src $dst; Write-Host ('Yedek alindi: ' + $dst)"
echo.
echo Yedegi gormek icin: db-yedek-goruntule.bat
pause
