"""Developer pages + listing management."""

from conftest import MEMBER2_EMAIL, db_row, login, seed_user


def _onboard(client, name="Dev One"):
    return client.post(
        "/developers/onboard",
        data={"display_name": name, "bio": "I build bots."},
        follow_redirects=False,
    )


def test_onboard_creates_profile_and_role(member_client):
    r = _onboard(member_client)
    assert r.status_code == 303
    row = db_row("SELECT * FROM developer_profiles WHERE user_id = (SELECT id FROM users WHERE email='member@example.com')")
    assert row is not None
    user = db_row("SELECT * FROM users WHERE email='member@example.com'")
    assert user["role"] == "developer"


def test_onboard_duplicate_409(member_client):
    _onboard(member_client)
    assert _onboard(member_client).status_code == 409


def test_dev_dashboard_redirects_without_profile(member_client):
    r = member_client.get("/dev", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/developers/onboard"


def test_create_publish_listing(member_client):
    _onboard(member_client)
    r = member_client.post(
        "/dev/bots",
        data={
            "name": "My Algo", "tagline": "t", "description": "d",
            "category": "expert-advisors", "price_cents": "5000",
            "payment_link_url": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    bot = db_row("SELECT * FROM bots WHERE slug='my-algo'")
    assert bot["status"] == "draft"
    member_client.post(f"/dev/bots/{bot['id']}/publish", follow_redirects=False)
    assert db_row("SELECT status FROM bots WHERE slug='my-algo'")["status"] == "published"
    api = member_client.get("/api/bots/my-algo").json()
    assert api["price_cents"] == 5000


def test_other_user_cannot_edit_listing(member_client):
    _onboard(member_client)
    member_client.post(
        "/dev/bots",
        data={"name": "Mine", "tagline": "", "description": "", "category": "general",
              "price_cents": "0", "payment_link_url": ""},
        follow_redirects=False,
    )
    bot = db_row("SELECT * FROM bots WHERE slug='mine'")
    member_client.post("/signout", follow_redirects=False)
    seed_user(MEMBER2_EMAIL)
    login(member_client, MEMBER2_EMAIL)
    r = member_client.post(
        f"/dev/bots/{bot['id']}/update",
        data={"name": "Hacked", "tagline": "", "description": "", "category": "general",
              "price_cents": "0", "payment_link_url": ""},
        follow_redirects=False,
    )
    assert r.status_code == 404
    assert db_row("SELECT name FROM bots WHERE slug='mine'")["name"] == "Mine"


def test_public_developer_page(member_client):
    _onboard(member_client, name="Star Dev")
    dev = db_row("SELECT * FROM developer_profiles WHERE display_name='Star Dev'")
    r = member_client.get(f"/developers/{dev['slug']}")
    assert r.status_code == 200
    assert "Star Dev" in r.text


def test_developors_index_lists_profiles(member_client):
    _onboard(member_client, name="Listed Dev")
    r = member_client.get("/developers")
    assert "Listed Dev" in r.text


def test_update_dev_profile(member_client):
    _onboard(member_client, name="Old Name")
    r = member_client.post(
        "/dev/profile",
        data={"display_name": "New Name", "bio": "Fresh bio indeed"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = db_row("SELECT * FROM developer_profiles WHERE display_name='New Name'")
    assert row is not None
    assert row["bio"] == "Fresh bio indeed"


def test_dev_profile_requires_profile_first(member_client):
    r = member_client.post(
        "/dev/profile",
        data={"display_name": "X", "bio": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/developers/onboard"
