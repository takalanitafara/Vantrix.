"""Checkout plumbing + licence grants (no real payments possible)."""

from conftest import (
    JSON_HEADERS,
    MEMBER2_EMAIL,
    db_row,
    login,
    seed_bot,
    seed_user,
)


def test_checkout_requires_auth(client):
    r = client.get("/api/checkout/quantora", headers=JSON_HEADERS, follow_redirects=False)
    assert r.status_code == 401


def test_checkout_without_payment_link_409(member_client):
    r = member_client.get("/api/checkout/quantora", headers=JSON_HEADERS)
    assert r.status_code == 409
    body = r.json()
    assert body["status"] == "payments_not_activated"


def test_checkout_with_link_redirects(member_client):
    seed_bot(slug="linked-bot", name="Linked", link="https://buy.stripe.com/test_123")
    r = member_client.get(
        "/api/checkout/linked-bot",
        headers=JSON_HEADERS,
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "https://buy.stripe.com/test_123"


def test_checkout_creates_pending_order(member_client):
    seed_bot(slug="linked-bot2", name="Linked2", link="https://buy.stripe.com/test_456", price=2500)
    member_client.get("/api/checkout/linked-bot2", headers=JSON_HEADERS, follow_redirects=False)
    order = db_row("SELECT * FROM orders WHERE status='pending'")
    assert order is not None
    assert order["amount_cents"] == 2500


def test_checkout_reuses_pending_order(member_client):
    seed_bot(slug="linked-bot3", name="Linked3", link="https://buy.stripe.com/test_789")
    for _ in range(3):
        member_client.get("/api/checkout/linked-bot3", headers=JSON_HEADERS, follow_redirects=False)
    row = db_row("SELECT COUNT(*) AS c FROM orders")
    assert row["c"] == 1


def _make_order(member_client):
    seed_bot(slug="pay-bot", name="Pay Bot", link="https://buy.stripe.com/pay", price=9900)
    member_client.get("/api/checkout/pay-bot", headers=JSON_HEADERS, follow_redirects=False)
    return db_row("SELECT * FROM orders WHERE status='pending'")


def test_confirm_grants_licence(member_client):
    order = _make_order(member_client)
    r = member_client.post(f"/api/checkout/confirm/{order['ref']}")
    assert r.status_code == 200
    body = r.json()
    assert body["order_status"] == "completed"
    assert body["license_key"].startswith("QV-")


def test_confirm_idempotent(member_client):
    order = _make_order(member_client)
    first = member_client.post(f"/api/checkout/confirm/{order['ref']}").json()
    second = member_client.post(f"/api/checkout/confirm/{order['ref']}").json()
    assert first["license_key"] == second["license_key"]
    assert db_row("SELECT COUNT(*) AS c FROM licenses")["c"] == 1


def test_confirm_page_renders(member_client):
    order = _make_order(member_client)
    r = member_client.get(f"/checkout/confirm/{order['ref']}")
    assert r.status_code == 200
    assert "Order confirmed" in r.text
    assert "QV-" in r.text


def test_my_bots_lists_licence(member_client):
    order = _make_order(member_client)
    lic = member_client.post(f"/api/checkout/confirm/{order['ref']}").json()
    r = member_client.get("/account/my-bots")
    assert r.status_code == 200
    assert lic["license_key"] in r.text


def test_confirm_foreign_order_404(member_client):
    order = _make_order(member_client)
    seed_user(MEMBER2_EMAIL)
    member_client.post("/signout", follow_redirects=False)
    login(member_client, MEMBER2_EMAIL)
    r = member_client.post(f"/api/checkout/confirm/{order['ref']}", headers=JSON_HEADERS)
    assert r.status_code == 404
