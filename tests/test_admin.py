"""Admin dashboard + moderation."""

from conftest import JSON_HEADERS, MEMBER_EMAIL, db_row, login, seed_user


def test_admin_forbidden_for_member(member_client):
    r = member_client.get("/admin", follow_redirects=False)
    assert r.status_code == 403


def test_admin_forbidden_for_anonymous(public_client):
    r = public_client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/signin"


def test_admin_owner_200(owner_client):
    r = owner_client.get("/admin")
    assert r.status_code == 200
    assert "Finance overview" in r.text
    assert "not real revenue" in r.text.lower()


def test_set_role(owner_client):
    uid = seed_user(MEMBER_EMAIL)
    owner_client.post(
        f"/admin/users/{uid}/role", data={"role": "admin"}, follow_redirects=False
    )
    assert db_row("SELECT role FROM users WHERE id=?", uid)["role"] == "admin"


def test_feature_toggle(owner_client):
    bot = db_row("SELECT * FROM bots WHERE slug='candlewise'")
    owner_client.post(
        f"/admin/bots/{bot['id']}/feature", data={"featured": "1"}, follow_redirects=False
    )
    featured = owner_client.get("/api/bots", params={"featured": "true"}).json()
    assert "candlewise" in [b["slug"] for b in featured["bots"]]


def test_status_change_hides_listing(owner_client):
    bot = db_row("SELECT * FROM bots WHERE slug='pipspilot'")
    owner_client.post(
        f"/admin/bots/{bot['id']}/status", data={"status": "delisted"}, follow_redirects=False
    )
    assert owner_client.get("/api/bots/pipspilot").status_code == 404


def test_admin_can_confirm_order(owner_client, member_client):
    from conftest import seed_bot
    seed_bot(slug="admin-pay", name="Admin Pay", link="https://buy.stripe.com/x", price=100)
    member_client.get("/api/checkout/admin-pay", headers=JSON_HEADERS, follow_redirects=False)
    order = db_row("SELECT * FROM orders WHERE status='pending'")
    # switch to owner session on the same client is messy: use owner_client
    owner_client.post(f"/admin/orders/{order['ref']}/confirm", follow_redirects=False)
    assert db_row("SELECT status FROM orders WHERE id=?", order["id"])["status"] == "completed"
    assert db_row("SELECT COUNT(*) AS c FROM licenses")["c"] == 1


def test_admin_sees_sample_finance_rows(owner_client):
    r = owner_client.get("/admin")
    assert "Plumbing gross" in r.text
    assert "Free" in r.text  # products/plans table
