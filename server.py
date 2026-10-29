#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YazilimSec local SQLite server.

Çalıştırma:
    python server.py
    python server.py --port 3001
    python server.py --site "C:\\baska\\yol\\site.html"

Sunucu açıldıktan sonra:
    http://127.0.0.1:3000/
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import sys
import threading
import time; from pathlib import Path; BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_FILE = BASE_DIR / "yaz_l_mse_tam_platform_aray_z.html"
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SITE_FILE = BASE_DIR.parent / "yaz_l_mse_tam_platform_aray_z.html"
DEFAULT_DB_FILE = BASE_DIR / "data" / "yazilimsec.db"
MAX_BODY_BYTES = 30 * 1024 * 1024  # 30 MB (base64 logolar için rahat sınır)
MAX_FORM_BYTES = 16 * 1024

SESSION_COOKIE = "yz_admin_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
_DEFAULT_ADMIN_PATH = "/kurumsal-giris-7e81773b"
ADMIN_PATH = (os.environ.get("YAZILIMSEC_ADMIN_PATH") or _DEFAULT_ADMIN_PATH).strip()
if not ADMIN_PATH.startswith("/"):
    ADMIN_PATH = "/" + ADMIN_PATH
ADMIN_PATH = ADMIN_PATH.rstrip("/")
if ADMIN_PATH in ("", "/") or ADMIN_PATH.startswith("/api"):
    ADMIN_PATH = _DEFAULT_ADMIN_PATH
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 10 * 60
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024

LOGIN_LOCK = threading.Lock()
LOGIN_FAILURES: dict[str, list[float]] = {}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    name         TEXT PRIMARY KEY,
    short_name   TEXT,
    long_name    TEXT,
    icon         TEXT,
    color        TEXT,
    description  TEXT,
    photo        TEXT,
    keywords     TEXT NOT NULL DEFAULT '[]',
    features     TEXT NOT NULL DEFAULT '{}',
    pros         TEXT NOT NULL DEFAULT '[]',
    cons         TEXT NOT NULL DEFAULT '[]',
    popular      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS software (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    vendor        TEXT,
    website       TEXT,
    category      TEXT,
    rating        REAL NOT NULL DEFAULT 0,
    reviews_count INTEGER NOT NULL DEFAULT 0,
    price         REAL NOT NULL DEFAULT 0,
    low_price     REAL NOT NULL DEFAULT 0,
    high_price    REAL NOT NULL DEFAULT 0,
    badge         TEXT,
    logo_file     TEXT,
    logo_data     TEXT,
    logo_bg       TEXT,
    popular       INTEGER NOT NULL DEFAULT 0,
    features      TEXT NOT NULL DEFAULT '{}',
    description   TEXT,
    pros          TEXT NOT NULL DEFAULT '[]',
    cons          TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS software_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    software_id TEXT NOT NULL,
    name        TEXT,
    title       TEXT,
    text        TEXT,
    rating      REAL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (software_id) REFERENCES software(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pending_reviews (
    id          TEXT PRIMARY KEY,
    software_id TEXT,
    name        TEXT,
    title       TEXT,
    text        TEXT,
    rating      REAL,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS approved_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    software_id TEXT,
    name        TEXT,
    title       TEXT,
    text        TEXT,
    rating      REAL,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS activity_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    action     TEXT NOT NULL,
    detail     TEXT
);

CREATE TABLE IF NOT EXISTS admin_auth (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    username      TEXT NOT NULL UNIQUE,
    salt          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    n             INTEGER NOT NULL,
    r             INTEGER NOT NULL,
    p             INTEGER NOT NULL,
    dklen         INTEGER NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires ON admin_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_software_category ON software(category);
CREATE INDEX IF NOT EXISTS idx_software_reviews_software ON software_reviews(software_id);
CREATE INDEX IF NOT EXISTS idx_pending_reviews_software ON pending_reviews(software_id);
CREATE INDEX IF NOT EXISTS idx_approved_reviews_software ON approved_reviews(software_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: Path) -> None:
    conn = db_connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def generate_strong_password(length: int = 28) -> str:
    """En az bir büyük/küçük harf, rakam ve sembol içeren güçlü şifre üretir."""
    groups = [
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "abcdefghijkmnopqrstuvwxyz",
        "23456789",
        "!@#$%^&*()-_=+[]{}?",
    ]
    alphabet = "".join(groups)
    rng = secrets.SystemRandom()
    chars = [rng.choice(group) for group in groups]
    chars.extend(rng.choice(alphabet) for _ in range(max(0, length - len(chars))))
    rng.shuffle(chars)
    return "".join(chars)


def generate_strong_username() -> str:
    """Tahmin edilmesi zor, rastgele bir yönetici kullanıcı adı üretir."""
    return "yz_" + secrets.token_hex(8)


def _password_digest(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
        maxmem=SCRYPT_MAXMEM,
    )


def set_admin_password(db_path: Path, password: str, username: str = "admin") -> None:
    if not password or len(password) < 12:
        raise ValueError("Admin şifresi en az 12 karakter olmalıdır.")
    salt = secrets.token_bytes(16)
    digest = _password_digest(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    conn = db_connect(db_path)
    try:
        conn.execute("DELETE FROM admin_auth")
        conn.execute(
            """
            INSERT INTO admin_auth
                (id, username, salt, password_hash, n, r, p, dklen, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(digest).decode("ascii"),
                SCRYPT_N,
                SCRYPT_R,
                SCRYPT_P,
                SCRYPT_DKLEN,
                utc_now(),
            ),
        )
        # Şifre değişince eski oturumların tamamı geçersiz olur.
        conn.execute("DELETE FROM admin_sessions")
        conn.commit()
    finally:
        conn.close()


def admin_auth_exists(db_path: Path) -> bool:
    conn = db_connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM admin_auth").fetchone()
        return bool(row and row["n"] > 0)
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_admin_username(db_path: Path) -> str | None:
    conn = db_connect(db_path)
    try:
        row = conn.execute("SELECT username FROM admin_auth WHERE id = 1").fetchone()
        return str(row["username"]) if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def verify_admin_password(db_path: Path, username: str, password: str) -> bool:
    conn = db_connect(db_path)
    try:
        row = conn.execute("SELECT * FROM admin_auth WHERE id = 1").fetchone()
    except sqlite3.Error:
        row = None
    finally:
        conn.close()

    # Kullanıcı adı yanlış olsa bile scrypt çalıştırarak zamanlama farkını azalt.
    if row:
        try:
            salt = base64.b64decode(row["salt"])
            expected = base64.b64decode(row["password_hash"])
            n, r, p, dklen = row["n"], row["r"], row["p"], row["dklen"]
        except (ValueError, TypeError):
            salt, expected = b"\0" * 16, b"\0" * SCRYPT_DKLEN
            n, r, p, dklen = SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN
    else:
        salt, expected = b"\0" * 16, b"\0" * SCRYPT_DKLEN
        n, r, p, dklen = SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN

    try:
        actual = _password_digest(password, salt, n, r, p, dklen)
    except (ValueError, MemoryError):
        return False

    if not row:
        return False
    user_ok = hmac.compare_digest(str(row["username"]).encode("utf-8"), username.encode("utf-8"))
    pass_ok = hmac.compare_digest(actual, expected)
    return user_ok and pass_ok


def ensure_admin_auth(db_path: Path) -> str | None:
    """İlk çalıştırmada güçlü kullanıcı adı ve şifre üretip hash'ini veritabanına yazar."""
    if admin_auth_exists(db_path):
        return None
    username = os.environ.get("YAZILIMSEC_ADMIN_USERNAME") or generate_strong_username()
    password = os.environ.get("YAZILIMSEC_ADMIN_PASSWORD") or generate_strong_password()
    set_admin_password(db_path, password, username)
    password_file = BASE_DIR / "ADMIN-ILK-SIFRE.txt"
    try:
        password_file.write_text(
            "YazilimSec ilk yonetici girisi\n"
            f"Kullanici adi: {username}\n"
            f"Sifre: {password}\n"
            f"Giris: http://127.0.0.1:3000{ADMIN_PATH}\n\n"
            "Bu dosyayı şifreyi ezberledikten sonra silin.\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    print("=" * 64)
    print("YÖNETİCİ GİRİŞİ OLUŞTURULDU (yalnızca bir kez gösterilir):")
    print(f"  Kullanıcı adı: {username}")
    print(f"  Şifre       : {password}")
    print(f"  Giriş       : http://127.0.0.1:3000{ADMIN_PATH}")
    print(f"  Dosya       : {password_file}")
    print("=" * 64)
    return password


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_admin_session(db_path: Path, username: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=SESSION_TTL_SECONDS)
    conn = db_connect(db_path)
    try:
        conn.execute(
            "DELETE FROM admin_sessions WHERE expires_at <= ?",
            (now.isoformat(timespec="seconds"),),
        )
        conn.execute(
            "INSERT INTO admin_sessions (token_hash, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (
                _token_hash(token),
                username,
                now.isoformat(timespec="seconds"),
                expires.isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def validate_admin_session(db_path: Path, token: str | None) -> str | None:
    if not token:
        return None
    conn = db_connect(db_path)
    try:
        row = conn.execute(
            "SELECT username, expires_at FROM admin_sessions WHERE token_hash = ?",
            (_token_hash(token),),
        ).fetchone()
        if not row:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
        except ValueError:
            conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))
            conn.commit()
            return None
        if expires <= datetime.now(timezone.utc):
            conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))
            conn.commit()
            return None
        return str(row["username"])
    finally:
        conn.close()


def delete_admin_session(db_path: Path, token: str | None) -> None:
    if not token:
        return
    conn = db_connect(db_path)
    try:
        conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (_token_hash(token),))
        conn.commit()
    finally:
        conn.close()


def clear_all_admin_sessions(db_path: Path) -> None:
    """Sunucu yeniden başladığında tüm admin oturumlarını geçersiz kılar."""
    conn = db_connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM admin_sessions").fetchone()
        if row and row["n"]:
            conn.execute("DELETE FROM admin_sessions")
            conn.commit()
    finally:
        conn.close()


def login_is_locked(ip: str) -> bool:
    now = time.time()
    with LOGIN_LOCK:
        attempts = [stamp for stamp in LOGIN_FAILURES.get(ip, []) if now - stamp < LOGIN_LOCKOUT_SECONDS]
        LOGIN_FAILURES[ip] = attempts
        return len(attempts) >= LOGIN_MAX_FAILURES


def record_login_failure(ip: str) -> None:
    now = time.time()
    with LOGIN_LOCK:
        attempts = [stamp for stamp in LOGIN_FAILURES.get(ip, []) if now - stamp < LOGIN_LOCKOUT_SECONDS]
        attempts.append(now)
        LOGIN_FAILURES[ip] = attempts


def clear_login_failures(ip: str) -> None:
    with LOGIN_LOCK:
        LOGIN_FAILURES.pop(ip, None)


def json_load(value, default):
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def state_is_empty(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS n FROM software").fetchone()
    return not row or row["n"] == 0


def get_state(db_path: Path):
    conn = db_connect(db_path)
    try:
        if state_is_empty(conn):
            return None

        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM settings")
        }

        categories = []
        for row in conn.execute("SELECT * FROM categories ORDER BY rowid"):
            categories.append({
                "name": row["name"],
                "short": row["short_name"] or row["name"],
                "long": row["long_name"] or row["name"],
                "icon": row["icon"] or "fa-layer-group",
                "color": row["color"] or "blue",
                "desc": row["description"] or "",
                "photo": row["photo"] or "",
                "keywords": json_load(row["keywords"], []),
                "features": json_load(row["features"], {}),
                "pros": json_load(row["pros"], []),
                "cons": json_load(row["cons"], []),
                "popular": bool(row["popular"]),
            })

        software_list = []
        for row in conn.execute("SELECT * FROM software ORDER BY rowid"):
            reviews = [
                {
                    "name": r["name"] or "",
                    "title": r["title"] or "",
                    "text": r["text"] or "",
                    "rating": r["rating"] if r["rating"] is not None else 0,
                }
                for r in conn.execute(
                    "SELECT name, title, text, rating FROM software_reviews "
                    "WHERE software_id = ? ORDER BY sort_order, id",
                    (row["id"],),
                )
            ]
            software_list.append({
                "id": row["id"],
                "name": row["name"],
                "vendor": row["vendor"] or "",
                "website": row["website"] or "",
                "category": row["category"] or "",
                "rating": row["rating"] if row["rating"] is not None else 0,
                "reviewsCount": row["reviews_count"] if row["reviews_count"] is not None else 0,
                "price": row["price"] if row["price"] is not None else 0,
                "lowPrice": row["low_price"] if row["low_price"] is not None else 0,
                "highPrice": row["high_price"] if row["high_price"] is not None else 0,
                "badge": row["badge"] or "",
                "logoFile": row["logo_file"],
                "logoData": row["logo_data"],
                "logoBg": row["logo_bg"] or "",
                "popular": bool(row["popular"]),
                "features": json_load(row["features"], {}),
                "desc": row["description"] or "",
                "pros": json_load(row["pros"], []),
                "cons": json_load(row["cons"], []),
                "reviews": reviews,
            })

        pending_reviews = [
            {
                "id": row["id"],
                "softwareId": row["software_id"] or "genel",
                "name": row["name"] or "",
                "title": row["title"] or "Kullanıcı",
                "rating": row["rating"] if row["rating"] is not None else 5,
                "text": row["text"] or "",
                "createdAt": row["created_at"] or "",
            }
            for row in conn.execute("SELECT * FROM pending_reviews ORDER BY rowid")
        ]

        approved_reviews = [
            {
                "softwareId": row["software_id"] or "genel",
                "name": row["name"] or "",
                "title": row["title"] or "Kullanıcı",
                "rating": row["rating"] if row["rating"] is not None else 5,
                "text": row["text"] or "",
                "createdAt": row["created_at"] or "",
            }
            for row in conn.execute("SELECT * FROM approved_reviews ORDER BY rowid")
        ]

        return {
            "version": 2,
            "siteId": settings.get("siteId") or "",
            "popularInitialized": settings.get("popularInitialized") == "true",
            "savedAt": settings.get("savedAt") or utc_now(),
            "softwareList": software_list,
            "categories": categories,
            "pendingReviews": pending_reviews,
            "approvedUserReviews": approved_reviews,
            "siteLogoData": settings.get("siteLogoData") or None,
        }
    finally:
        conn.close()


def normalized_rating(value):
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return value


def review_signature(reviews):
    return [
        (
            str(r.get("name") or ""),
            str(r.get("title") or ""),
            str(r.get("text") or ""),
            normalized_rating(r.get("rating")),
        )
        for r in (reviews or [])
        if isinstance(r, dict)
    ]


def summarize_changes(old_state, new_state):
    """İki durum arasındaki farkı insan okunur işlem kayıtlarına çevirir."""
    if old_state is None:
        software_count = len(new_state.get("softwareList") or [])
        category_count = len(new_state.get("categories") or [])
        return [("İlk kayıt", f"Veritabanı ilk kez oluşturuldu: {software_count} yazılım, {category_count} kategori.")]

    changes = []

    old_soft = {s.get("id"): s for s in (old_state.get("softwareList") or []) if isinstance(s, dict) and s.get("id")}
    new_soft = {s.get("id"): s for s in (new_state.get("softwareList") or []) if isinstance(s, dict) and s.get("id")}

    for sid, item in new_soft.items():
        if sid not in old_soft:
            changes.append(("Yazılım eklendi", item.get("name") or sid))
    for sid, item in old_soft.items():
        if sid not in new_soft:
            changes.append(("Yazılım silindi", item.get("name") or sid))

    for sid in set(old_soft) & set(new_soft):
        old_item = old_soft[sid]
        new_item = new_soft[sid]
        fields = []
        for key, label in (
            ("name", "ad"),
            ("vendor", "firma"),
            ("website", "web sitesi"),
            ("category", "kategori"),
            ("price", "fiyat"),
            ("rating", "puan"),
            ("badge", "rozet"),
            ("popular", "popüler"),
        ):
            if old_item.get(key) != new_item.get(key):
                fields.append(f"{label}: {old_item.get(key)} → {new_item.get(key)}")
        if (old_item.get("features") or {}) != (new_item.get("features") or {}):
            fields.append("özellikler değişti")
        if (old_item.get("logoFile") != new_item.get("logoFile")) or (old_item.get("logoData") != new_item.get("logoData")):
            fields.append("logo değişti")
        if str(old_item.get("desc") or "") != str(new_item.get("desc") or ""):
            fields.append("açıklama değişti")
        if (old_item.get("pros") or []) != (new_item.get("pros") or []):
            fields.append("artı maddeleri değişti")
        if (old_item.get("cons") or []) != (new_item.get("cons") or []):
            fields.append("eksi maddeleri değişti")
        if review_signature(old_item.get("reviews")) != review_signature(new_item.get("reviews")):
            fields.append(f"yorumlar değişti ({len(old_item.get('reviews') or [])} → {len(new_item.get('reviews') or [])})")
        if fields:
            changes.append(("Yazılım güncellendi", f"{new_item.get('name') or sid} ({', '.join(fields)})"))

    old_cats = {c.get("name"): c for c in (old_state.get("categories") or []) if isinstance(c, dict) and c.get("name")}
    new_cats = {c.get("name"): c for c in (new_state.get("categories") or []) if isinstance(c, dict) and c.get("name")}

    for name in new_cats:
        if name not in old_cats:
            changes.append(("Kategori eklendi", name))
    for name in old_cats:
        if name not in new_cats:
            changes.append(("Kategori silindi", name))

    for name in set(old_cats) & set(new_cats):
        old_cat = old_cats[name]
        new_cat = new_cats[name]
        fields = []
        for key, label in (
            ("short", "kısa ad"),
            ("long", "uzun ad"),
            ("icon", "ikon"),
            ("color", "renk"),
            ("desc", "açıklama"),
            ("popular", "popüler"),
        ):
            if old_cat.get(key) != new_cat.get(key):
                fields.append(f"{label}: {old_cat.get(key)} → {new_cat.get(key)}")
        if (old_cat.get("keywords") or []) != (new_cat.get("keywords") or []):
            fields.append("anahtar kelimeler değişti")
        if (old_cat.get("features") or {}) != (new_cat.get("features") or {}):
            fields.append("özellikler değişti")
        if fields:
            changes.append(("Kategori güncellendi", f"{name} ({', '.join(fields)})"))

    def review_key(review):
        return f"{review.get('name')}|{review.get('text')}|{normalized_rating(review.get('rating'))}"

    old_pending = {review_key(r): r for r in (old_state.get("pendingReviews") or []) if isinstance(r, dict)}
    new_pending = {review_key(r): r for r in (new_state.get("pendingReviews") or []) if isinstance(r, dict)}
    old_approved = {review_key(r): r for r in (old_state.get("approvedUserReviews") or []) if isinstance(r, dict)}
    new_approved = {review_key(r): r for r in (new_state.get("approvedUserReviews") or []) if isinstance(r, dict)}

    for key, review in new_pending.items():
        if key not in old_pending and key not in old_approved:
            changes.append(("Yorum eklendi", f"{review.get('name', '')} - {str(review.get('text', ''))[:70]}"))
    for key, review in new_approved.items():
        if key not in old_approved:
            changes.append(("Yorum onaylandı", f"{review.get('name', '')} - {str(review.get('text', ''))[:70]}"))
    for key, review in old_approved.items():
        if key not in new_approved:
            if key in new_pending:
                changes.append(("Yorum onayı kaldırıldı", f"{review.get('name', '')} - {str(review.get('text', ''))[:70]}"))
            else:
                changes.append(("Onaylı yorum silindi", f"{review.get('name', '')} - {str(review.get('text', ''))[:70]}"))
    for key, review in old_pending.items():
        if key not in new_pending and key not in new_approved:
            changes.append(("Yorum reddedildi/silindi", f"{review.get('name', '')} - {str(review.get('text', ''))[:70]}"))

    if (old_state.get("siteLogoData") or "") != (new_state.get("siteLogoData") or ""):
        changes.append(("Site logosu güncellendi", "Üst başlık logosu değiştirildi."))

    return changes


def get_activity(db_path: Path, limit: int = 200):
    conn = db_connect(db_path)
    try:
        safe_limit = max(1, min(500, int(limit)))
        rows = conn.execute(
            "SELECT id, created_at, action, detail FROM activity_log ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "action": row["action"],
                "detail": row["detail"] or "",
            }
            for row in rows
        ]
    finally:
        conn.close()


def as_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def save_state(db_path: Path, state: dict) -> str:
    if not isinstance(state, dict):
        raise ValueError("Geçersiz durum verisi.")

    software_list = state.get("softwareList")
    categories = state.get("categories")
    if not isinstance(software_list, list):
        raise ValueError("softwareList bir dizi olmalıdır.")
    if not isinstance(categories, list):
        raise ValueError("categories bir dizi olmalıdır.")

    saved_at = as_text(state.get("savedAt")) or utc_now()
    old_state = get_state(db_path)
    conn = db_connect(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM software_reviews")
            conn.execute("DELETE FROM software")
            conn.execute("DELETE FROM pending_reviews")
            conn.execute("DELETE FROM approved_reviews")
            conn.execute("DELETE FROM categories")
            conn.execute("DELETE FROM settings")

            for cat in categories:
                if not isinstance(cat, dict) or not as_text(cat.get("name")):
                    continue
                conn.execute(
                    """
                    INSERT INTO categories
                        (name, short_name, long_name, icon, color, description, photo,
                         keywords, features, pros, cons, popular)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        as_text(cat.get("name")),
                        as_text(cat.get("short")) or as_text(cat.get("name")),
                        as_text(cat.get("long")) or as_text(cat.get("name")),
                        as_text(cat.get("icon")) or "fa-layer-group",
                        as_text(cat.get("color")) or "blue",
                        as_text(cat.get("desc")),
                        as_text(cat.get("photo")),
                        json_dump(cat.get("keywords") if isinstance(cat.get("keywords"), list) else []),
                        json_dump(cat.get("features") if isinstance(cat.get("features"), dict) else {}),
                        json_dump(cat.get("pros") if isinstance(cat.get("pros"), list) else []),
                        json_dump(cat.get("cons") if isinstance(cat.get("cons"), list) else []),
                        1 if cat.get("popular") else 0,
                    ),
                )

            for item in software_list:
                if not isinstance(item, dict) or not as_text(item.get("id")):
                    continue
                software_id = as_text(item.get("id"))
                conn.execute(
                    """
                    INSERT INTO software
                        (id, name, vendor, website, category, rating, reviews_count,
                         price, low_price, high_price, badge, logo_file, logo_data,
                         logo_bg, popular, features, description, pros, cons)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        software_id,
                        as_text(item.get("name")),
                        as_text(item.get("vendor")),
                        as_text(item.get("website")),
                        as_text(item.get("category")),
                        as_float(item.get("rating")),
                        as_int(item.get("reviewsCount")),
                        as_float(item.get("price")),
                        as_float(item.get("lowPrice")),
                        as_float(item.get("highPrice")),
                        as_text(item.get("badge")),
                        item.get("logoFile"),
                        item.get("logoData"),
                        as_text(item.get("logoBg")),
                        1 if item.get("popular") else 0,
                        json_dump(item.get("features") if isinstance(item.get("features"), dict) else {}),
                        as_text(item.get("desc")),
                        json_dump(item.get("pros") if isinstance(item.get("pros"), list) else []),
                        json_dump(item.get("cons") if isinstance(item.get("cons"), list) else []),
                    ),
                )

                reviews = item.get("reviews")
                if isinstance(reviews, list):
                    for index, review in enumerate(reviews):
                        if not isinstance(review, dict):
                            continue
                        conn.execute(
                            """
                            INSERT INTO software_reviews
                                (software_id, name, title, text, rating, sort_order)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                software_id,
                                as_text(review.get("name")),
                                as_text(review.get("title")),
                                as_text(review.get("text")),
                                as_float(review.get("rating")),
                                index,
                            ),
                        )

            for review in state.get("pendingReviews") or []:
                if not isinstance(review, dict):
                    continue
                review_id = as_text(review.get("id")) or f"pr-{utc_now()}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pending_reviews
                        (id, software_id, name, title, text, rating, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        as_text(review.get("softwareId")) or "genel",
                        as_text(review.get("name")),
                        as_text(review.get("title")) or "Kullanıcı",
                        as_text(review.get("text")),
                        as_float(review.get("rating"), 5.0),
                        as_text(review.get("createdAt")) or utc_now(),
                    ),
                )

            for review in state.get("approvedUserReviews") or []:
                if not isinstance(review, dict):
                    continue
                conn.execute(
                    """
                    INSERT INTO approved_reviews
                        (software_id, name, title, text, rating, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        as_text(review.get("softwareId")) or "genel",
                        as_text(review.get("name")),
                        as_text(review.get("title")) or "Kullanıcı",
                        as_text(review.get("text")),
                        as_float(review.get("rating"), 5.0),
                        as_text(review.get("createdAt")) or utc_now(),
                    ),
                )

            settings = {
                "siteId": as_text(state.get("siteId")),
                "popularInitialized": "true" if state.get("popularInitialized") else "false",
                "savedAt": saved_at,
                "siteLogoData": as_text(state.get("siteLogoData")),
            }
            for key, value in settings.items():
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))

            # Değişiklikleri işlem geçmişine yaz.
            stamp = utc_now()
            for action, detail in summarize_changes(old_state, state):
                conn.execute(
                    "INSERT INTO activity_log (created_at, action, detail) VALUES (?, ?, ?)",
                    (stamp, action, detail),
                )
            conn.execute(
                "DELETE FROM activity_log WHERE id NOT IN "
                "(SELECT id FROM activity_log ORDER BY id DESC LIMIT 500)"
            )

        return saved_at
    finally:
        conn.close()


class YazilimSecHandler(BaseHTTPRequestHandler):
    server_version = "YazilimSecSQLite/1.0"
    site_file: Path = DEFAULT_SITE_FILE
    db_file: Path = DEFAULT_DB_FILE

    def _send_bytes(
        self,
        data: bytes,
        content_type: str,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def _send_json(self, payload, status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(data, "application/json; charset=utf-8", status, extra_headers)

    def _redirect(self, location: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _session_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _authenticated_username(self) -> str | None:
        return validate_admin_session(self.db_file, self._session_token())

    def _require_auth(self) -> bool:
        if self._authenticated_username():
            return True
        self._send_json(
            {"error": "Yetkisiz. Lütfen yönetim giriş adresinden giriş yapın."},
            401,
        )
        return False

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and origin != "null":
            host = self.headers.get("Host", "")
            if origin not in (f"http://{host}", f"https://{host}"):
                return False
        # Bazı yerel tarayıcılar form POST isteklerinde Origin: null gönderebilir.
        # Asıl kaynak kontrolünü Sec-Fetch-Site ile yap.
        sec_fetch_site = self.headers.get("Sec-Fetch-Site")
        if sec_fetch_site and sec_fetch_site not in ("same-origin", "none"):
            return False
        return True

    def _read_form(self) -> dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("Geçersiz Content-Length.")
        if length <= 0:
            raise ValueError("Form gövdesi boş.")
        if length > MAX_FORM_BYTES:
            raise ValueError("Form gövdesi çok büyük.")
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {key: values[0] for key, values in parse_qs(raw, keep_blank_values=True).items()}

    def _serve_login(self, error_code: str | None = None) -> None:
        messages = {
            "1": "Kullanıcı adı veya şifre hatalı.",
            "required": "Kullanıcı adı ve şifre zorunludur.",
            "locked": "Çok fazla hatalı deneme yapıldı. 10 dakika sonra tekrar deneyin.",
            "expired": "Oturum süresi doldu. Tekrar giriş yapın.",
        }
        message = messages.get(error_code or "", "")
        error_html = f'<div class="error">{html.escape(message)}</div>' if message else ""
        page = f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>YazılımSeç Kurumsal Giriş</title>
  <style>
    :root {{ color-scheme: dark; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      padding: 24px; background: radial-gradient(circle at top, #1e3a5f 0, #0f172a 45%, #020617 100%);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #e2e8f0;
    }}
    .card {{ width: 100%; max-width: 420px; background: #ffffff; color: #0f172a; border-radius: 24px; padding: 34px 30px; box-shadow: 0 24px 70px rgba(0,0,0,.45); }}
    .brand {{ font-size: 24px; font-weight: 800; letter-spacing: -0.04em; color: #0f172a; margin-bottom: 18px; }}
    .brand span {{ color: #3b82f6; }}
    h1 {{ font-size: 21px; margin: 0 0 6px; }}
    .sub {{ margin: 0 0 20px; color: #64748b; font-size: 13px; line-height: 1.5; }}
    .error {{ background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 12px; padding: 11px 13px; font-size: 13px; font-weight: 600; margin-bottom: 16px; }}
    label {{ display: block; font-size: 12px; font-weight: 700; color: #334155; margin: 14px 0 7px; }}
    input {{ width: 100%; border: 1px solid #cbd5e1; border-radius: 12px; padding: 12px 13px; font-size: 15px; outline: none; background: #f8fafc; color: #0f172a; }}
    input:focus {{ border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,.16); background: #fff; }}
    button {{ width: 100%; margin-top: 20px; border: 0; border-radius: 999px; padding: 13px 18px; background: #3b82f6; color: #fff; font-size: 14px; font-weight: 800; cursor: pointer; }}
    button:hover {{ background: #2563eb; }}
    .note {{ margin: 18px 0 0; color: #94a3b8; font-size: 11px; line-height: 1.5; text-align: center; }}
  </style>
</head>
<body>
  <main class="card">
    <div class="brand">Yazılım<span>Seç</span></div>
    <h1>Kurumsal Giriş</h1>
    <p class="sub">Bu alan yalnızca yetkili kullanıcı içindir. Devam etmek için giriş yapın.</p>
    {error_html}
    <form method="post" action="/api/auth/login">
      <label for="username">Kullanıcı adı</label>
      <input id="username" name="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus>
      <label for="password">Şifre</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Giriş Yap</button>
    </form>
    <p class="note">Yetkisiz erişim girişimleri kaydedilir. Bu sayfa arama motorlarına kapalıdır.</p>
  </main>
</body>
</html>"""
        self._send_bytes(
            page.encode("utf-8"),
            "text/html; charset=utf-8",
            200,
            {"X-Robots-Tag": "noindex, nofollow", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"},
        )

    def _handle_login(self) -> None:
        if not self._origin_allowed():
            self._send_json({"error": "Geçersiz istek kaynağı."}, 403)
            return
        ip = self.client_address[0]
        if login_is_locked(ip):
            self._redirect(ADMIN_PATH + "?error=locked")
            return
        try:
            form = self._read_form()
        except ValueError:
            self._redirect(ADMIN_PATH + "?error=1")
            return
        username = (form.get("username") or "").strip()
        password = form.get("password") or ""
        if not username or not password:
            self._redirect(ADMIN_PATH + "?error=required")
            return
        if verify_admin_password(self.db_file, username, password):
            clear_login_failures(ip)
            token = create_admin_session(self.db_file, username)
            self._redirect(
                ADMIN_PATH,
                {"Set-Cookie": f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL_SECONDS}"},
            )
            return
        record_login_failure(ip)
        time.sleep(0.4)
        self._redirect(ADMIN_PATH + "?error=1")

    def _handle_logout(self) -> None:
        delete_admin_session(self.db_file, self._session_token())
        self._redirect(
            "/",
            {"Set-Cookie": f"{SESSION_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"},
        )

    def _serve_site(self, admin_authenticated: bool = False, admin_route: bool = False) -> None:
        if not self.site_file.exists():
            self._send_json({"error": f"Site dosyası bulunamadı: {self.site_file}"}, 404)
            return
        html_text = self.site_file.read_text(encoding="utf-8")
        # Siteye sadece bu sunucu üzerinden servis edildiğinde API modu işaretini ekle.
        # Admin yetkisi ve gizli rota bilgisi de sunucu tarafından enjekte edilir.
        admin_path_js = json.dumps(ADMIN_PATH) if admin_authenticated else "''"
        marker = (
            "<script>"
            "window.__YAZILIMSEC_SQLITE__=true;"
            f"window.__YAZILIMSEC_ADMIN_AUTH__={'true' if admin_authenticated else 'false'};"
            f"window.__YAZILIMSEC_ADMIN_ROUTE__={'true' if admin_route else 'false'};"
            f"window.__YAZILIMSEC_ADMIN_PATH__={admin_path_js};"
            "</script>"
        )
        if "</head>" in html_text:
            html_text = html_text.replace("</head>", marker + "</head>", 1)
        else:
            html_text = marker + html_text
        extra = {"X-Robots-Tag": "noindex, nofollow"} if admin_route else None
        self._send_bytes(html_text.encode("utf-8"), "text/html; charset=utf-8", 200, extra)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("Geçersiz Content-Length.")
        if length <= 0:
            raise ValueError("İstek gövdesi boş.")
        if length > MAX_BODY_BYTES:
            raise ValueError("İstek gövdesi çok büyük.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Geçersiz JSON: {exc}")
        if not isinstance(payload, dict):
            raise ValueError("JSON kökü bir nesne olmalıdır.")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        username = self._authenticated_username()

        if path == "/api/health":
            self._send_json({
                "ok": True,
                "database": str(self.db_file),
                "site": str(self.site_file),
                "admin_auth": admin_auth_exists(self.db_file),
            })
            return
        if path == "/api/auth/status":
            self._send_json({"authenticated": bool(username), "username": username})
            return
        if path == "/api/state":
            state = get_state(self.db_file)
            if state is None:
                self._send_json({"empty": True})
            else:
                # Bekleyen yorumlar yalnızca giriş yapmış yöneticiye gönderilir.
                if not username:
                    state["pendingReviews"] = []
                self._send_json(state)
            return
        if path == "/api/activity":
            if not self._require_auth():
                return
            limit = 200
            if query.get("limit"):
                try:
                    limit = int(query["limit"][0])
                except (TypeError, ValueError):
                    limit = 200
            self._send_json({"items": get_activity(self.db_file, limit)})
            return
        if path in (ADMIN_PATH, ADMIN_PATH + "/", ADMIN_PATH + "/index.html"):
            if username:
                self._serve_site(admin_authenticated=True, admin_route=True)
            else:
                error_code = (query.get("error") or [None])[0]
                self._serve_login(error_code)
            return
        if path in ("/", "/index.html", "/yaz_l_mse_tam_platform_aray_z.html"):
            self._serve_site(admin_authenticated=bool(username), admin_route=False)
            return
        if path == "/favicon.ico":
            self._send_bytes(b"", "image/x-icon", 204)
            return
        self._send_json({"error": "Bulunamadı."}, 404)

    def _save_from_request(self) -> None:
        if not self._require_auth():
            return
        if not self._origin_allowed():
            self._send_json({"error": "Geçersiz istek kaynağı."}, 403)
            return
        try:
            state = self._read_json()
            saved_at = save_state(self.db_file, state)
            self._send_json({"ok": True, "savedAt": saved_at})
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001 - yerel sunucu için açıklayıcı hata döndür
            print(f"[DB HATASI] {exc}", file=sys.stderr)
            self._send_json({"error": f"Veritabanı hatası: {exc}"}, 500)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._save_from_request()
            return
        self._send_json({"error": "Bulunamadı."}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/auth/login":
            self._handle_login()
            return
        if path == "/api/auth/logout":
            self._handle_logout()
            return
        if path in ("/api/state", "/api/seed"):
            self._save_from_request()
            return
        self._send_json({"error": "Bulunamadı."}, 404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YazilimSec yerel SQLite sunucusu")
    parser.add_argument("--host", default="127.0.0.1", help="Dinlenecek adres (varsayılan: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=3000, help="Port (varsayılan: 3000)")
    parser.add_argument("--site", default=str(DEFAULT_SITE_FILE), help="Servis edilecek HTML dosyası")
    parser.add_argument("--db", default=str(DEFAULT_DB_FILE), help="SQLite veritabanı dosyası")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    site_file = Path(args.site).expanduser().resolve()
    db_file = Path(args.db).expanduser().resolve()

    if not site_file.exists():
        print(f"HATA: Site dosyası bulunamadı: {site_file}", file=sys.stderr)
        return 1

    init_db(db_file)
    ensure_admin_auth(db_file)
    # PRD gereği: sunucu yeniden başlarsa önceki oturumlar geçersizdir.
    clear_all_admin_sessions(db_file)
    YazilimSecHandler.site_file = site_file
    YazilimSecHandler.db_file = db_file

    server = ThreadingHTTPServer(("0.0.0.0", args.port), YazilimSecHandler)
    print("=" * 64)
    print("YazilimSec SQLite sunucusu çalışıyor")
    print(f"Site      : http://{args.host}:{args.port}/")
    print(f"Giriş     : http://{args.host}:{args.port}{ADMIN_PATH}  (giriş gerekli)")
    print(f"HTML      : {site_file}")
    print(f"Veritabanı: {db_file}")
    print("Oturumlar : Sunucu başlangıcında sıfırlandı (yeniden giriş gerekir)")
    print("Durdurmak için Ctrl+C")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu durduruldu.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
