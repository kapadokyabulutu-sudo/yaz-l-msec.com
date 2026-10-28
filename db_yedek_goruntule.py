# YazilimSec yedek goruntuleyici
# Kullanim:
#   python db_yedek_goruntule.py            -> en yeni yedegi gosterir
#   python db_yedek_goruntule.py 2          -> listedeki 2. yedegi gosterir
#   python db_yedek_goruntule.py dosya.db   -> dosya adina gore yedegi gosterir

import glob
import os
import sqlite3
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

TABLES = [
    "software",
    "categories",
    "software_reviews",
    "pending_reviews",
    "approved_reviews",
    "activity_log",
]


def list_backups():
    files = glob.glob(os.path.join(DATA_DIR, "yazilimsec-*.db"))
    return sorted(files, key=os.path.getmtime, reverse=True)


def format_time(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d.%m.%Y %H:%M:%S")


def inspect_backup(path):
    print("=" * 64)
    print("Yedek dosyasi :", os.path.basename(path))
    print("Konum         :", path)
    print("Boyut         :", "%.1f KB" % (os.path.getsize(path) / 1024))
    print("Yedek zamani  :", format_time(path))
    print("-" * 64)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for table in TABLES:
            try:
                count = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                print("%-18s: %s" % (table, count))
            except sqlite3.Error:
                print("%-18s: (tablo yok)" % table)

        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", ("savedAt",)).fetchone()
            print("Son kayit      :", row["value"] if row else "-")
        except sqlite3.Error:
            print("Son kayit      : -")

        try:
            rows = conn.execute("SELECT name, category, price FROM software ORDER BY name").fetchall()
            print("-" * 64)
            print("Yazilimlar (%d):" % len(rows))
            for row in rows:
                print("  - %s | %s | %s TL" % (row["name"], row["category"] or "-", row["price"]))
        except sqlite3.Error as exc:
            print("Yazilimlar okunamadi:", exc)

        try:
            rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
            print("-" * 64)
            print("Kategoriler:", ", ".join(row["name"] for row in rows) if rows else "-")
        except sqlite3.Error:
            pass

        try:
            rows = conn.execute(
                "SELECT created_at, action, detail FROM activity_log ORDER BY id DESC LIMIT 10"
            ).fetchall()
            print("-" * 64)
            print("Son islemler:")
            if not rows:
                print("  (kayit yok)")
            for row in rows:
                detail = (row["detail"] or "")[:90]
                print("  - %s | %s | %s" % (row["created_at"], row["action"], detail))
        except sqlite3.Error:
            pass
    finally:
        conn.close()

    print("=" * 64)


def pick_backup(backups, choice):
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(backups):
            return backups[index]
        return None

    needle = choice.lower()
    for path in backups:
        name = os.path.basename(path).lower()
        if name == needle or needle in name:
            return path
    return None


def main():
    backups = list_backups()

    if not backups:
        print("Henuz yedek dosyasi yok.")
        print("Yedek almak icin: db-yedekle.bat")
        print("Klasor:", DATA_DIR)
        return

    print("Mevcut yedekler (en yeni ustte):")
    for index, path in enumerate(backups, 1):
        print("  %d) %s  (%s)" % (index, os.path.basename(path), format_time(path)))
    print()

    choice = " ".join(sys.argv[1:]).strip()
    if choice:
        target = pick_backup(backups, choice)
        if not target:
            print("Yedek bulunamadi:", choice)
            print("Listedeki numarayi veya dosya adini kullanabilirsin.")
            return
    else:
        target = backups[0]
        print("En yeni yedek aciliyor...")
        print()

    inspect_backup(target)


if __name__ == "__main__":
    main()
