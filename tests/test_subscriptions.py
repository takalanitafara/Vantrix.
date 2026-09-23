"""Subscription tiers (paid tiers stay unbillable)."""

from conftest import db_row


def test_plans_page(member_client):
    r = member_client.get("/account/subscriptions")
    assert r.status_code == 200
    assert "Free" in r.text
    assert "Pro" in r.text


def test_subscribe_free_activates(member_client):
    r = member_client.post(
        "/account/subscriptions",
        data={"plan_slug": "free"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "notice=subscribed" in r.headers["location"]
    row = db_row("SELECT * FROM user_subscriptions")
    assert row["status"] == "active"


def test_subscribe_paid_stays_pending(member_client):
    r = member_client.post(
        "/account/subscriptions",
        data={"plan_slug": "pro"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "paid_plan_pending_payments" in r.headers["location"]
    row = db_row("SELECT * FROM user_subscriptions")
    assert row["status"] == "pending"
