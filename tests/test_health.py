"""Health is public for deployment monitoring; static assets load without auth."""


def test_health_public_in_private_mode(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["service"] == "Vantrix"  # technical identifier, keep as-is
    assert data["status"] == "running"
    assert data["brand"] == "QuantVenue"


def test_health_public_in_public_mode(public_client):
    assert public_client.get("/health").status_code == 200


def test_static_css_open_in_private_mode(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert "QuantVenue" in r.text
