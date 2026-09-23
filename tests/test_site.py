"""Site finishing: error pages, favicon, robots, validation handling."""

import pytest


def test_robots_public_in_private_mode(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Disallow: /" in r.text


def test_favicon_svg(client):
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert "image/svg" in r.headers["content-type"]


def test_favicon_ico(client):
    assert client.get("/favicon.ico").status_code == 200


def test_html_404_page(public_client):
    r = public_client.get("/no-such-page")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    assert "404" in r.text
    assert "Back to marketplace" in r.text


def test_api_404_json(public_client):
    r = public_client.get("/api/no-such-endpoint")
    assert r.status_code == 404
    assert r.json()["error"]


def test_api_405_json(public_client):
    r = public_client.post("/api/bots")
    assert r.status_code == 405
    assert r.json()["error"]


def test_validation_error_html_422(public_client):
    r = public_client.post("/signup", data={}, follow_redirects=False)
    assert r.status_code == 422
    assert "check the form" in r.text


def test_validation_error_json_422(public_client):
    r = public_client.post("/api/bots/quantora/reviews", data={},
                           headers={"Accept": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]


def test_security_headers_present(public_client):
    r = public_client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_static_js_served(public_client):
    r = public_client.get("/static/app.js")
    assert r.status_code == 200
    assert "navtoggle" in r.text
