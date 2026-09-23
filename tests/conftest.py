import os

# Bootstrap env so the module-level app factory (server:app) never touches ./data
os.environ.setdefault("QUANTVENUE_DB_PATH", "/tmp/qv-conftest-bootstrap.db")
os.environ.setdefault("QUANTVENUE_SECRET_KEY", "test-secret")

import pytest
from fastapi.testclient import TestClient

from server import create_app, db as db_mod
from server.auth import hash_password

OWNER_EMAIL = "owner@example.com"
MEMBER_EMAIL = "member@example.com"
MEMBER2_EMAIL = "member2@example.com"
PASSWORD = "password123"
JSON_HEADERS = {"Accept": "application/json"}


def seed_user(email, role="user", name=None, password=PASSWORD):
    conn = db_mod.connect()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, display_name, role) "
            "VALUES (?, ?, ?, ?)",
            (email.lower(), hash_password(password), name or email.split("@")[0], role),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def seed_bot(
    slug="sample-bot",
    name="Sample Bot",
    status="published",
    link=None,
    featured=0,
    price=1000,
    category="general",
):
    conn = db_mod.connect()
    try:
        dev = conn.execute(
            "SELECT id FROM developer_profiles WHERE slug='quantvenue-labs'"
        ).fetchone()
        conn.execute(
            "INSERT INTO bots (slug, name, tagline, description, category, "
            "price_cents, developer_id, payment_link_url, status, featured) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                slug, name, "A test bot", "UniqueBody zinc-alloy-review text",
                category, price, dev["id"], link, status, featured,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def db_row(sql, *params):
    conn = db_mod.connect()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def login(client, email=MEMBER_EMAIL, password=PASSWORD):
    return client.post(
        "/signin",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """Shared private-mode env + fresh DB path. Sessions stay independent
    because each client fixture builds its own TestClient (cookie jar)."""
    monkeypatch.setenv("QUANTVENUE_DB_PATH", str(tmp_path / "qv.db"))
    monkeypatch.setenv("QUANTVENUE_PRIVATE_MODE", "true")
    monkeypatch.setenv("QUANTVENUE_ADMIN_EMAILS", OWNER_EMAIL)
    monkeypatch.setenv("QUANTVENUE_SECRET_KEY", "test-secret")
    from server import auth as auth_mod
    auth_mod._RESET_ATTEMPTS.clear()  # rate-limiter state is per-process


@pytest.fixture()
def client(app_env):
    return TestClient(create_app())


@pytest.fixture()
def owner_client(app_env):
    c = TestClient(create_app())
    r = c.post(
        "/signup",
        data={"email": OWNER_EMAIL, "password": PASSWORD, "display_name": "Owner"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return c


@pytest.fixture()
def public_client(app_env, monkeypatch):
    monkeypatch.setenv("QUANTVENUE_PRIVATE_MODE", "false")
    return TestClient(create_app())


@pytest.fixture()
def member_client(app_env, monkeypatch):
    monkeypatch.setenv("QUANTVENUE_PRIVATE_MODE", "false")
    c = TestClient(create_app())
    seed_user(MEMBER_EMAIL)
    r = login(c)
    assert r.status_code == 303, r.text
    return c
