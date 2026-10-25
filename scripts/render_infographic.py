"""Render docs/infographic/infographic.html to docs/images/pilot-infographic.jpg (needs Playwright).

    pip install playwright && playwright install chromium
    python scripts/render_infographic.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 790}, device_scale_factor=1.5)
    page.goto((ROOT / "docs" / "infographic" / "infographic.html").as_uri())
    page.wait_for_timeout(500)
    page.screenshot(path=str(ROOT / "docs" / "images" / "pilot-infographic.jpg"), quality=86, type="jpeg")
    browser.close()
print("wrote docs/images/pilot-infographic.jpg")
