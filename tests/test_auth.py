"""Accounts: signup, signin, sessions (public mode)."""

from conftest import MEMBER_EMAIL, PASSWORD, login, seed_user


def test_signup_creates_session(public_client):
    r = public_client.post(
        "/signup",
        data={"email": "new@example.com", "password": PASSWORD, "display_name": "New"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert public_client.get("/account", follow_redirects=False).status_code == 200


def test_signup_duplicate_email_409(public_client):
    seed_user(MEMBER_EMAIL)
    r = public_client.post(
        "/signup",
        data={"email": MEMBER_EMAIL, "password": PASSWORD, "display_name": "Dup"},
        follow_redirects=False,
    )
    assert r.status_code == 409


def test_signup_short_password_400(public_client):
    r = public_client.post(
        "/signup",
        data={"email": "short@example.com", "password": "abc", "display_name": "S"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_signin_wrong_password_401(public_client):
    seed_user(MEMBER_EMAIL)
    r = login(public_client, MEMBER_EMAIL, "wrong-password")
    assert r.status_code == 401


def test_signin_unknown_email_401(public_client):
    r = login(public_client, "ghost@example.com")
    assert r.status_code == 401


def test_signin_ok(member_client):
    assert member_client.get("/account", follow_redirects=False).status_code == 200


def test_account_requires_auth(public_client):
    r = public_client.get("/account", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/signin"


def test_signout_clears_session(member_client):
    assert member_client.post("/signout", follow_redirects=False).status_code == 303
    r = member_client.get("/account", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/signin"
