"""SQLite persistence for the QuantVenue platform layer.

Schema/filenames are part of the technical contract and must not be renamed.
The database file lives under QUANTVENUE_DATA_DIR / QUANTVENUE_DB_PATH so a
persistent volume can be mounted over it in production.
"""

from __future__ import annotations

import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user', -- user | developer | admin
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS developer_profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER UNIQUE REFERENCES users(id), -- NULL for curated house listings
    slug         TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    bio          TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    tagline         TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    category        TEXT DEFAULT 'general',
    price_cents     INTEGER NOT NULL DEFAULT 0,
    developer_id    INTEGER REFERENCES developer_profiles(id),
    payment_link_url TEXT,                       -- Stripe payment link (plumbing until real payments)
    status          TEXT DEFAULT 'draft',        -- draft | published | delisted
    featured        INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ref          TEXT UNIQUE NOT NULL,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    bot_id       INTEGER NOT NULL REFERENCES bots(id),
    amount_cents INTEGER NOT NULL,
    status       TEXT DEFAULT 'pending', -- pending | completed | cancelled
    created_at   TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS licenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key TEXT UNIQUE NOT NULL,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    bot_id      INTEGER NOT NULL REFERENCES bots(id),
    order_id    INTEGER REFERENCES orders(id),
    status      TEXT DEFAULT 'active', -- active | revoked
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id     INTEGER NOT NULL REFERENCES bots(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body       TEXT DEFAULT '',
    status     TEXT DEFAULT 'pending', -- pending | approved | hidden
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (bot_id, user_id)
);

CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL DEFAULT 0,
    period      TEXT DEFAULT 'month'
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER UNIQUE NOT NULL REFERENCES users(id),
    plan_id    INTEGER NOT NULL REFERENCES plans(id),
    status     TEXT DEFAULT 'active', -- active | pending | cancelled
    created_at TEXT DEFAULT (datetime('now'))
);
"""

# Sample marketplace listings so a fresh deployment is browsable. No payment
# links on purpose: activating real payments is explicitly owner-deferred.
SAMPLE_BOTS = [
    (
        "quantora",
        "Quantora",
        "Multi-strategy expert adviser with adaptive risk envelopes.",
        "Quantora is an independent trading bot sold and accessed through "
        "QuantVenue. It runs outside this platform: QuantVenue handles listing, "
        "checkout and licensing only and never executes trades.",
        "expert-advisors",
        12900,
    ),
    (
        "candlewise",
        "Candlewise",
        "Price-action signal toolkit for discretionary traders.",
        "Candlewise ships annotated setup alerts and session statistics as a "
        "standalone application. Purchases here grant a licence key only.",
        "indicators",
        4900,
    ),
    (
        "pipspilot",
        "PipsPilot",
        "Lightweight journaling and session planner for manual traders.",
        "PipsPilot is an independent utility bot listed on QuantVenue. "
        "No broker connection is made by this marketplace.",
        "utilities",
        2900,
    ),
]


def connect() -> sqlite3.Connection:
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS c FROM plans").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO plans (slug, name, price_cents, period) VALUES (?, ?, ?, ?)",
            [("free", "Free", 0, "month"), ("pro", "Pro", 4900, "month")],
        )
    if conn.execute("SELECT COUNT(*) AS c FROM bots").fetchone()["c"] == 0:
        cur = conn.execute(
            "INSERT INTO developer_profiles (user_id, slug, display_name, bio) "
            "VALUES (NULL, 'quantvenue-labs', 'QuantVenue Labs', "
            "'Curated house listings shipped with the platform.')"
        )
        dev_id = cur.lastrowid
        for slug, name, tagline, description, category, price in SAMPLE_BOTS:
            conn.execute(
                "INSERT INTO bots (slug, name, tagline, description, category, "
                "price_cents, developer_id, status, featured) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'published', ?)",
                (slug, name, tagline, description, category, price, dev_id,
                 1 if slug == "quantora" else 0),
            )
