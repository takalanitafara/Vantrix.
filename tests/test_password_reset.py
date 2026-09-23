"""Forgot-password / password-reset flow (owner/admin only, secure delivery)."""

from fastapi.testclient import TestClient

from conftest import (
    MEMBER_EMAIL,
    OWNER_EMAIL,
    PASSWORD,
    db_row,
    login,
    seed_user,
)
from server import create_app, db as db_mod
from server.auth import create_reset_token, reset_eligible


def _user(email):
    conn = db_mod.connect()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()


def _token_for(email):
    return create_reset_token_from_mod(email)


def create_reset_token_from_mod(email):
    conn = db_mod.connect()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return create_reset_token(conn, user)
    finally:
        conn.close()


def _reset(client, token, new="brand-new-pass-1", confirm=None):
    return client.post(
        "/reset-password",
        data={
            "token": token,
            "new_password": new,
            "confirm_password": confirm if confirm is not None else new,
        },
        follow_redirects=False,
    )


# ------------------------------------------------------------------ pages

def test_forgot_page_open_in_private_mode(client):
    r = client.get("/forgot-password")
    assert r.status_code == 200
    assert "Forgot password" in r.text


def test_signin_links_to_forgot(client):
    r = client.get("/signin")
    assert 'href="/forgot-password"' in r.text


def test_reset_page_form_has_no_account_info(client):
    seed_user(OWNER_EMAIL)
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    r = client.get(f"/reset-password?token={raw}")
    assert r.status_code == 200
    assert "Set a new password" in r.text
    assert OWNER_EMAIL not in r.text  # never reveal the account


# ------------------------------------------------------- forgot-password

def test_forgot_neutral_response_and_no_token_in_body(client):
    seed_user(OWNER_EMAIL)
    r = client.post(
        "/forgot-password", data={"email": OWNER_EMAIL}, follow_redirects=False
    )
    assert r.status_code == 200
    row = db_row("SELECT * FROM password_reset_tokens")
    assert row is not None  # token was issued...
    # ...but the response never contains any token material
    assert "token=" not in r.text
    assert row["token_hash"] not in r.text
    # anti-enumeration: unknown email gets the identical sent=True page
    r2 = client.post(
        "/forgot-password", data={"email": "nobody@example.com"}, follow_redirects=False
    )
    assert r2.status_code == 200
    assert "server console" in r.text
    assert ("server console" in r.text) == ("server console" in r2.text)


def test_forgot_logs_reset_link_but_never_password(client, capsys):
    seed_user(OWNER_EMAIL)
    client.post("/forgot-password", data={"email": OWNER_EMAIL}, follow_redirects=False)
    captured = capsys.readouterr()
    assert "/reset-password?token=" in captured.err  # operator channel
    assert PASSWORD not in captured.err              # never the password
    assert PASSWORD not in captured.out


def test_forgot_non_admin_gets_no_token(client):
    seed_user(MEMBER_EMAIL)
    r = client.post(
        "/forgot-password", data={"email": MEMBER_EMAIL}, follow_redirects=False
    )
    assert r.status_code == 200  # neutral response
    assert db_row("SELECT COUNT(*) AS c FROM password_reset_tokens")["c"] == 0


def test_forgot_unknown_email_no_token(client):
    client.post(
        "/forgot-password", data={"email": "ghost@example.com"}, follow_redirects=False
    )
    assert db_row("SELECT COUNT(*) AS c FROM password_reset_tokens")["c"] == 0


def test_forgot_rate_limited(client):
    seed_user(OWNER_EMAIL)
    for _ in range(5):
        r = client.post(
            "/forgot-password", data={"email": OWNER_EMAIL}, follow_redirects=False
        )
        assert r.status_code == 200
    r = client.post(
        "/forgot-password", data={"email": OWNER_EMAIL}, follow_redirects=False
    )
    assert r.status_code == 429


# ------------------------------------------------------------- resetting

def test_reset_changes_password(client):
    seed_user(OWNER_EMAIL)
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    r = _reset(client, raw, new="brand-new-pass-1")
    assert r.status_code == 303
    assert "notice=password_reset" in r.headers["location"]
    # old password rejected, new one works
    assert login(client, OWNER_EMAIL, PASSWORD).status_code == 401
    assert login(client, OWNER_EMAIL, "brand-new-pass-1").status_code == 303


def test_reset_token_single_use(client):
    seed_user(OWNER_EMAIL)
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    assert _reset(client, raw).status_code == 303
    r = _reset(client, raw, new="another-pass-99")
    assert r.status_code == 404


def test_reset_invalid_token_404(client):
    assert _reset(client, "not-a-real-token").status_code == 404
    assert _reset(client, "").status_code == 404


def test_reset_expired_token_404(client):
    seed_user(OWNER_EMAIL)
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    conn = db_mod.connect()
    try:
        conn.execute(
            "UPDATE password_reset_tokens SET expires_at = datetime('now', '-1 minute')"
        )
        conn.commit()
    finally:
        conn.close()
    assert _reset(client, raw).status_code == 404


def test_reset_passwords_must_match(client):
    seed_user(OWNER_EMAIL)
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    r = _reset(client, raw, new="brand-new-pass-1", confirm="different-pass-1")
    assert r.status_code == 400
    # token still unused
    assert login(client, OWNER_EMAIL, PASSWORD).status_code == 303


def test_reset_password_min_length(client):
    seed_user(OWNER_EMAIL)
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    assert _reset(client, raw, new="short").status_code == 400


def test_reset_kills_existing_sessions(client):
    seed_user(OWNER_EMAIL)
    assert login(client, OWNER_EMAIL).status_code == 303  # session A
    raw = create_reset_token_from_mod(OWNER_EMAIL)
    assert _reset(client, raw, new="brand-new-pass-1").status_code == 303
    # the pre-reset session cookie is now dead (private gate returns auth error)
    r = client.get("/account", follow_redirects=False)
    assert r.status_code == 401


# ------------------------------------------------- signed-in change (admin)

def test_admin_can_change_password_after_signin(client):
    seed_user(OWNER_EMAIL, role="admin")
    assert login(client, OWNER_EMAIL).status_code == 303
    r = client.post(
        "/account/password",
        data={"current_password": PASSWORD, "new_password": "changed-admin-1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "notice=password_changed" in r.headers["location"]
    client.post("/signout", follow_redirects=False)
    assert login(client, OWNER_EMAIL, "changed-admin-1").status_code == 303
    assert login(client, OWNER_EMAIL, PASSWORD).status_code == 401


def test_change_password_kills_other_sessions(app_env):
    client_a = TestClient(create_app())
    client_b = TestClient(create_app())
    seed_user(OWNER_EMAIL)
    assert login(client_a, OWNER_EMAIL).status_code == 303
    assert login(client_b, OWNER_EMAIL).status_code == 303
    assert client_b.get("/account", follow_redirects=False).status_code == 200

    r = client_a.post(
        "/account/password",
        data={"current_password": PASSWORD, "new_password": "changed-admin-1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # device A stays signed in; device B is signed out everywhere
    assert client_a.get("/account", follow_redirects=False).status_code == 200
    assert client_b.get("/account", follow_redirects=False).status_code == 401


def test_change_password_invalidates_reset_tokens(member_client):
    conn = db_mod.connect()
    try:
        user = conn.execute("SELECT * FROM users LIMIT 1").fetchone()
        raw = create_reset_token(conn, user)
    finally:
        conn.close()
    # pending reset links die when the account password changes via /account
    r = member_client.post(
        "/account/password",
        data={"current_password": PASSWORD, "new_password": "member-new-1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert _reset(member_client, raw, new="sneaky-pass-1").status_code == 404


def test_reset_eligible_scope():
    assert reset_eligible(None) is False


def test_privacy_signup_still_blocked(client):
    r = client.post(
        "/signup",
        data={"email": "public@example.com", "password": PASSWORD, "display_name": "P"},
        follow_redirects=False,
    )
    assert r.status_code == 403
