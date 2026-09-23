"""QUANTVENUE_PRIVATE_MODE gate: fail-closed, owner/admin-only."""

from conftest import JSON_HEADERS, MEMBER_EMAIL, OWNER_EMAIL, PASSWORD, login, seed_user


def test_unset_mode_is_private(client, monkeypatch):
    monkeypatch.delenv("QUANTVENUE_PRIVATE_MODE", raising=False)
    assert client.get("/", follow_redirects=False).status_code == 401


def test_garbage_mode_is_private(client, monkeypatch):
    monkeypatch.setenv("QUANTVENUE_PRIVATE_MODE", "banana")
    assert client.get("/", follow_redirects=False).status_code == 401


def test_home_requires_auth(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 401
    assert "private" in r.text.lower()


def test_api_unauthenticated_json_error(client):
    r = client.get("/api/bots")
    assert r.status_code == 401
    assert r.json()["error"] == "authentication required"


def test_bot_page_unauthenticated(client):
    assert client.get("/bot/quantora", follow_redirects=False).status_code == 401


def test_signin_page_open(client):
    assert client.get("/signin").status_code == 200


def test_signup_page_shows_private_notice(client):
    r = client.get("/signup")
    assert r.status_code == 200
    assert "disabled" in r.text.lower()


def test_public_signup_blocked(client):
    r = client.post(
        "/signup",
        data={"email": "intruder@example.com", "password": PASSWORD, "display_name": "X"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    r = client.post(
        "/signup",
        data={"email": "intruder@example.com", "password": PASSWORD, "display_name": "X"},
        headers=JSON_HEADERS,
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_owner_signup_allowed(client):
    r = client.post(
        "/signup",
        data={"email": OWNER_EMAIL, "password": PASSWORD, "display_name": "Owner"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 200


def test_non_admin_signin_blocked():
    pass  # covered below with client fixture


def test_member_signin_blocked_in_private(client):
    seed_user(MEMBER_EMAIL)
    r = login(client)
    assert r.status_code == 403
    assert "private" in r.text.lower()


def test_admin_email_promotes_role_at_signin(client):
    # seeded as ordinary user, but email is in QUANTVENUE_ADMIN_EMAILS
    seed_user(OWNER_EMAIL, role="user")
    r = login(client, OWNER_EMAIL)
    assert r.status_code == 303
    assert client.get("/admin", follow_redirects=False).status_code == 200


def test_owner_session_grants_app_access(owner_client):
    assert owner_client.get("/", follow_redirects=False).status_code == 200
    assert owner_client.get("/api/bots").status_code == 200
    assert owner_client.get("/bot/quantora", follow_redirects=False).status_code == 200


def test_non_owner_session_denied_everywhere(public_client, monkeypatch):
    seed_user(MEMBER_EMAIL)
    assert login(public_client).status_code == 303
    monkeypatch.setenv("QUANTVENUE_PRIVATE_MODE", "true")
    assert public_client.get("/", follow_redirects=False).status_code == 403
    assert public_client.get("/api/bots").status_code == 403
    assert public_client.get("/account", follow_redirects=False).status_code == 403
    assert public_client.get("/admin", follow_redirects=False).status_code == 403


def test_signout_open(client):
    assert client.post("/signout", follow_redirects=False).status_code == 303


def test_public_mode_opens_catalog(public_client):
    assert public_client.get("/", follow_redirects=False).status_code == 200
    assert public_client.get("/api/bots").status_code == 200
