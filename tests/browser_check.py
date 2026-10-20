"""Real Chromium checks. Run with BASE_URL and optional ARTIFACT_DIR."""
import hashlib
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

base = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
out = Path(os.environ.get("ARTIFACT_DIR", "artifacts"))
out.mkdir(parents=True, exist_ok=True)
expected_html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text()
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get("CHROMIUM_EXECUTABLE_PATH"),
        args=["--no-sandbox", "--disable-dev-shm-usage", "--no-zygote"],
    )
    for label, width, height in [("desktop", 1440, 1000), ("mobile", 390, 844), ("small-mobile", 320, 740)]:
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(base + "/", wait_until="networkidle")
        assert response.status == 200, response.status
        assert response.text() == expected_html, "Served homepage does not match checked-out revision"
        assert page.title() == "Vantrix — Intelligent Trading Systems"
        assert page.locator("h1").is_visible()
        assert page.locator("#server-status").inner_text() == "Not checked"
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"
        assert page.locator(".dashbody").evaluate("e => getComputedStyle(e).display") == "grid"
        columns = page.locator(".dashbody").evaluate("e => getComputedStyle(e).gridTemplateColumns").split()
        assert len(columns) == (3 if width > 800 else 1), columns
        page.get_by_role("button", name="Check Server", exact=True).click()
        page.wait_for_function("document.querySelector('#server-value').textContent === 'Online'")
        assert page.locator("#result").inner_text() == "Server: running"
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        page.wait_for_timeout(100)
        page.screenshot(path=str(out / f"{label}.png"), full_page=True)
        # Test HTTP error and recovery in the actual browser, not only mocks of the DOM.
        page.route("**/health", lambda route: route.fulfill(status=503, body='{}'))
        page.get_by_role("button", name="Check Server", exact=True).click()
        page.wait_for_function("document.querySelector('#server-value').textContent === 'Unavailable'")
        assert page.get_by_role("button", name="Check Server", exact=True).is_enabled()
        page.unroute("**/health")
        page.get_by_role("button", name="Check Server", exact=True).click()
        page.wait_for_function("document.querySelector('#server-value').textContent === 'Online'")
        assert not errors, errors
        results.append({"viewport": label, "width": width, "passed": True, "page_errors": errors})
        page.close()
    response = browser.new_context().request.get(base + "/health")
    assert response.status == 200
    assert response.json() == {"ok": True, "service": "Vantrix", "status": "running"}
    response = browser.new_context().request.get(base + "/does-not-exist")
    assert response.status == 404, response.status
    browser.close()
(out / "browser-results.json").write_text(json.dumps({"base_url": base, "html_sha256": hashlib.sha256(expected_html.encode()).hexdigest(), "results": results}, indent=2))
print(json.dumps(results, indent=2))
