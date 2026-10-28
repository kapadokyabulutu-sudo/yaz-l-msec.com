-- YazilimSec SQLite şeması
-- server.py bu şemayı ilk çalıştırmada otomatik oluşturur.
-- Elle incelemek veya başka bir SQLite aracında açmak için kullanılabilir.

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
