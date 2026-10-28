#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YazilimSec yönetici giriş bilgilerini günceller.

Kullanım:
    python admin_sifre.py
    python admin_sifre.py --password "YeniGucluSifre!2026"
    python admin_sifre.py --username yz_yeni_kullanici
    python admin_sifre.py --db "C:\\...\\yazilimsec.db"

Şifre verilmezse 28 karakterlik güçlü bir şifre üretilir.
Kullanıcı adı verilmezse mevcut kullanıcı adı korunur.
Giriş adresi server.py içindeki gizli ADMIN_PATH değeridir.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from server import (
    ADMIN_PATH,
    DEFAULT_DB_FILE,
    generate_strong_password,
    generate_strong_username,
    get_admin_username,
    init_db,
    set_admin_password,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="YazilimSec yönetici giriş bilgilerini güncelle")
    parser.add_argument("--password", default="", help="Yeni şifre (boşsa güçlü şifre üretilir)")
    parser.add_argument("--username", default="", help="Yeni kullanıcı adı (boşsa mevcut ad korunur; yoksa güçlü ad üretilir)")
    parser.add_argument("--db", default=str(DEFAULT_DB_FILE), help="SQLite veritabanı yolu")
    parser.add_argument("--no-file", action="store_true", help="ADMIN-SIFRE.txt dosyasına yazma")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    init_db(db_path)

    username = args.username.strip() or get_admin_username(db_path) or generate_strong_username()
    password = args.password or generate_strong_password()
    try:
        set_admin_password(db_path, password, username)
    except ValueError as exc:
        print(f"HATA: {exc}")
        return 1

    print("=" * 64)
    print("YAZILIMSEC YÖNETİCİ GİRİŞİ GÜNCELLENDİ")
    print("=" * 64)
    print(f"Kullanıcı adı: {username}")
    print(f"Yeni şifre   : {password}")
    print(f"Giriş adresi : http://127.0.0.1:3000{ADMIN_PATH}")
    print("=" * 64)
    print("Not: Giriş bilgileri değişince mevcut oturumlar kapatılır.")

    if not args.no_file:
        password_file = db_path.parent.parent / "ADMIN-SIFRE.txt"
        try:
            password_file.write_text(
                "YazilimSec yonetici girisi\n"
                f"Kullanici adi: {username}\n"
                f"Sifre: {password}\n"
                f"Giris: http://127.0.0.1:3000{ADMIN_PATH}\n\n"
                "Bu dosyayı şifreyi ezberledikten sonra silin.\n",
                encoding="utf-8",
            )
            print(f"Şifre dosyası: {password_file}")
        except OSError as exc:
            print(f"Uyarı: Şifre dosyası yazılamadı: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
