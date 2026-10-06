"""Capture README screenshots of a running ShopMotion instance.

Usage:
    pip install playwright && playwright install chromium   # or pass --channel chrome
    flask seed-demo && python run.py                         # in another terminal
    python scripts/take_screenshots.py --base http://127.0.0.1:5000
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = [
    ("dashboard", "/"),
    ("live-monitoring", "/live"),
    ("traffic-analytics", "/analytics/traffic"),
    ("heatmap", "/analytics/heatmap"),
    ("dwell-time", "/analytics/dwell"),
    ("reports", "/reports"),
    ("store-layout", "/store-layout"),
    ("camera-setup", "/cameras"),
    ("settings", "/settings"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "screenshots"))
    parser.add_argument("--channel", default=None, help="use an installed browser, e.g. chrome or msedge")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)

        page.goto(f"{args.base}/login")
        page.screenshot(path=str(out / "login.png"))
        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click("#submit")
        page.wait_for_url(f"{args.base}/")

        for name, path in PAGES:
            page.goto(f"{args.base}{path}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1200)  # let Chart.js animations finish
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
            print("saved", name)

        browser.close()


if __name__ == "__main__":
    main()
