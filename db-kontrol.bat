@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -c "import sqlite3, os; p=r'data\yazilimsec.db'; print('Veritabani:', os.path.abspath(p)); c=sqlite3.connect(p); [print(f'{t}: ' + str(c.execute('select count(*) from ' + t).fetchone()[0])) for t in ['software','categories','software_reviews','pending_reviews','approved_reviews','activity_log']]; s=c.execute('select value from settings where key=?', ('savedAt',)).fetchone(); print('Son kayit:', s[0] if s else '-'); print('Son islemler:'); [print(' -', r[0], '|', r[1], '|', (r[2] or '')[:80]) for r in c.execute('select created_at, action, detail from activity_log order by id desc limit 5')]; c.close()"
echo.
pause
