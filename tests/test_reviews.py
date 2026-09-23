"""Reviews + moderation."""

from conftest import JSON_HEADERS, db_row


def _post_review(client, slug="quantora", rating=5, body="zinc-alloy-review"):
    return client.post(
        f"/bot/{slug}/reviews",
        data={"rating": str(rating), "body": body},
        follow_redirects=False,
    )


def test_review_starts_pending_and_hidden(member_client):
    r = _post_review(member_client)
    assert r.status_code == 303
    page = member_client.get("/bot/quantora")
    # not rendered as a published review card (only in the author's edit form)
    assert '<div class="review">' not in page.text
    row = db_row("SELECT * FROM reviews")
    assert row["status"] == "pending"


def test_api_review_created_pending(member_client):
    r = member_client.post(
        "/api/bots/quantora/reviews",
        data={"rating": "4", "body": "zinc-alloy-review"},
        headers=JSON_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"


def test_api_review_rating_bounds(member_client):
    r = member_client.post(
        "/api/bots/quantora/reviews",
        data={"rating": "9", "body": "x"},
        headers=JSON_HEADERS,
    )
    assert r.status_code == 400


def test_form_review_rating_clamped(member_client):
    _post_review(member_client, rating=9)
    row = db_row("SELECT * FROM reviews")
    assert row["rating"] == 5


def test_resubmit_resets_to_pending(member_client, owner_client):
    _post_review(member_client)
    review = db_row("SELECT * FROM reviews")
    owner_client.post(
        f"/admin/reviews/{review['id']}/moderate",
        data={"status": "approved"},
        follow_redirects=False,
    )
    assert db_row("SELECT * FROM reviews")["status"] == "approved"
    _post_review(member_client, rating=3, body="zinc-alloy-review")
    assert db_row("SELECT * FROM reviews")["status"] == "pending"


def test_approved_review_visible(owner_client):
    # owner posts and self-approves via admin
    _post_review(owner_client)
    review = db_row("SELECT * FROM reviews")
    owner_client.post(
        f"/admin/reviews/{review['id']}/moderate",
        data={"status": "approved"},
        follow_redirects=False,
    )
    page = owner_client.get("/bot/quantora")
    assert "zinc-alloy-review" in page.text
