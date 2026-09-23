"""Marketplace catalog API + pages."""

from conftest import seed_bot


def test_api_lists_seeded_published(public_client):
    data = public_client.get("/api/bots").json()
    slugs = {b["slug"] for b in data["bots"]}
    assert {"quantora", "candlewise", "pipspilot"} <= slugs


def test_api_search(public_client):
    data = public_client.get("/api/bots", params={"q": "quantora"}).json()
    assert [b["slug"] for b in data["bots"]] == ["quantora"]


def test_api_category_filter(public_client):
    data = public_client.get("/api/bots", params={"category": "indicators"}).json()
    assert [b["slug"] for b in data["bots"]] == ["candlewise"]


def test_api_featured_filter(public_client):
    data = public_client.get("/api/bots", params={"featured": "true"}).json()
    assert [b["slug"] for b in data["bots"]] == ["quantora"]


def test_api_bot_detail(public_client):
    bot = public_client.get("/api/bots/quantora").json()
    assert bot["name"] == "Quantora"
    assert bot["price_cents"] == 12900
    assert bot["developer"] == "QuantVenue Labs"


def test_api_bot_unknown_404(public_client):
    r = public_client.get("/api/bots/does-not-exist")
    assert r.status_code == 404


def test_bot_page_renders(public_client):
    r = public_client.get("/bot/quantora")
    assert r.status_code == 200
    assert "Quantora" in r.text
    assert "Buy now" in r.text


def test_draft_listing_hidden_from_api(public_client):
    seed_bot(slug="secret-draft", name="Secret Draft", status="draft")
    slugs = [b["slug"] for b in public_client.get("/api/bots").json()["bots"]]
    assert "secret-draft" not in slugs
    assert public_client.get("/api/bots/secret-draft").status_code == 404


def test_delisted_hidden(public_client):
    seed_bot(slug="gone-bot", name="Gone", status="delisted")
    assert public_client.get("/api/bots/gone-bot").status_code == 404


def test_catalog_page_search_ui(public_client):
    r = public_client.get("/", params={"q": "pips"})
    assert r.status_code == 200
    assert "PipsPilot" in r.text
    assert 'href="/bot/quantora"' not in r.text  # no other listings in results
