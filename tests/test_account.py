"""Account profile + password management."""

from conftest import PASSWORD, login


def test_profile_update(member_client):
    r = member_client.post(
        "/account/profile",
        data={"display_name": "Renamed Person"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "notice=profile_updated" in r.headers["location"]
    page = member_client.get("/account")
    assert "Renamed Person" in page.text


def test_profile_empty_name_400(member_client):
    r = member_client.post(
        "/account/profile", data={"display_name": "   "}, follow_redirects=False
    )
    assert r.status_code == 400


def test_password_change(member_client):
    r = member_client.post(
        "/account/password",
        data={"current_password": PASSWORD, "new_password": "newpass-123"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "notice=password_changed" in r.headers["location"]
    member_client.post("/signout", follow_redirects=False)
    assert login(member_client, password="newpass-123").status_code == 303


def test_password_change_wrong_current(member_client):
    r = member_client.post(
        "/account/password",
        data={"current_password": "not-my-password", "new_password": "newpass-123"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_password_change_too_short(member_client):
    r = member_client.post(
        "/account/password",
        data={"current_password": PASSWORD, "new_password": "short"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_profile_requires_auth(public_client):
    r = public_client.post(
        "/account/profile",
        data={"display_name": "X"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/signin"
