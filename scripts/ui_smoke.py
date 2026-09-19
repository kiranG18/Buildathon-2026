"""Browser smoke test: signs in, visits every route at 1366x768, records console errors and saves screenshots to docs/screenshots.

Needs Playwright and Microsoft Edge (or Chromium): python scripts/ui_smoke.py [base_url]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
ROUTES = [
    "/overview", "/approvals", "/campaigns", "/campaigns/C1/overview", "/campaigns/C1/board", "/campaigns/C1/activity", "/campaigns/C1/prompts", "/campaigns/C1/knowledge",
    "/campaigns/C1/config", "/campaigns/C4/overview", "/campaigns/new", "/prospects", "/prospects/dana-whitfield", "/prospects/sam-okafor", "/conversations", "/activity",
    "/analytics", "/prompts", "/knowledge", "/settings/integrations", "/settings/reps", "/settings/suppression", "/settings/demo",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(BASE)
        page.wait_for_selector(".login")
        page.screenshot(path=str(OUT / "login.png"))
        page.click("[data-a=loginAs][data-email='ava@helix.demo']")
        page.wait_for_selector(".app")
        for r in ROUTES:
            page.evaluate(f"go('{r}')")
            page.wait_for_timeout(350)
            html = page.inner_html("#view")
            if "This screen hit an error" in html:
                errors.append(f"route {r}: render error")
            page.screenshot(path=str(OUT / (r.strip("/").replace("/", "_") + ".png")))
        browser.close()
    for e in errors:
        print(e)
    print("errors:", len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
