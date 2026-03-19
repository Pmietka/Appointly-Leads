"""
Google Maps Lead Scraper
Scrapes business listings from Google Maps for a given search query.
Extracts: name, phone, address, website, rating, review count, category, hours.
"""

import asyncio
import csv
import json
import re
import sys
import time
import argparse
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError


@dataclass
class Lead:
    name: str = ""
    phone: str = ""
    address: str = ""
    website: str = ""
    rating: str = ""
    reviews: str = ""
    category: str = ""
    hours: str = ""
    maps_url: str = ""


async def scrape_listing(page: Page, url: str) -> Lead:
    """Open a single business listing and extract all fields."""
    lead = Lead(maps_url=url)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # Business name
        try:
            lead.name = await page.locator("h1").first.inner_text(timeout=5000)
        except Exception:
            pass

        # Rating
        try:
            rating_el = page.locator('[jslog*="star-rating"] span[aria-label]').first
            label = await rating_el.get_attribute("aria-label", timeout=3000)
            if label:
                m = re.search(r"([\d.]+)", label)
                if m:
                    lead.rating = m.group(1)
        except Exception:
            pass

        # Reviews count
        try:
            reviews_el = page.locator('button[jsaction*="reviewChart"]').first
            txt = await reviews_el.inner_text(timeout=3000)
            m = re.search(r"([\d,]+)", txt)
            if m:
                lead.reviews = m.group(1).replace(",", "")
        except Exception:
            pass

        # Category
        try:
            cat_el = page.locator('button[jsaction*="category"]').first
            lead.category = await cat_el.inner_text(timeout=3000)
        except Exception:
            pass

        # Address
        try:
            addr_el = page.locator('[data-item-id="address"]').first
            lead.address = await addr_el.get_attribute("aria-label", timeout=3000)
            if lead.address:
                lead.address = lead.address.replace("Address: ", "").strip()
        except Exception:
            pass

        # Phone
        try:
            phone_el = page.locator('[data-tooltip="Copy phone number"]').first
            lead.phone = await phone_el.get_attribute("aria-label", timeout=3000)
            if lead.phone:
                lead.phone = lead.phone.replace("Phone: ", "").strip()
        except Exception:
            pass

        # Website
        try:
            web_el = page.locator('[data-item-id="authority"]').first
            lead.website = await web_el.get_attribute("href", timeout=3000) or ""
        except Exception:
            pass

        # Hours (today)
        try:
            hours_el = page.locator('[data-hide-tooltip-on-mouse-move="true"] .fontBodyMedium span').first
            lead.hours = await hours_el.inner_text(timeout=3000)
        except Exception:
            pass

    except Exception as e:
        print(f"  [warn] Error scraping {url}: {e}", file=sys.stderr)

    return lead


async def search_google_maps(query: str, max_results: int, headless: bool) -> list[Lead]:
    """Search Google Maps and return leads."""
    leads: list[Lead] = []
    search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()

        print(f"Searching: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Dismiss consent screen if present (EU)
        try:
            accept = page.locator('button:has-text("Accept all")')
            if await accept.count() > 0:
                await accept.first.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Collect listing URLs by scrolling the results panel
        listing_urls: list[str] = []
        results_panel = page.locator('[role="feed"]')

        print(f"Collecting up to {max_results} listings...")
        scroll_attempts = 0
        max_scroll = max_results * 3  # generous scroll budget

        while len(listing_urls) < max_results and scroll_attempts < max_scroll:
            links = await page.locator('a[href*="/maps/place/"]').all()
            seen = set(listing_urls)
            for link in links:
                href = await link.get_attribute("href")
                if href and href not in seen and "/maps/place/" in href:
                    listing_urls.append(href)
                    seen.add(href)
                    if len(listing_urls) >= max_results:
                        break

            if len(listing_urls) >= max_results:
                break

            # Check for "end of list" message
            end_msg = await page.locator("text=You've reached the end of the list").count()
            if end_msg > 0:
                break

            # Scroll the results feed
            try:
                await results_panel.evaluate("el => el.scrollBy(0, 800)")
            except Exception:
                await page.keyboard.press("End")
            await page.wait_for_timeout(1500)
            scroll_attempts += 1

        listing_urls = listing_urls[:max_results]
        print(f"Found {len(listing_urls)} listings. Scraping details...")

        for i, url in enumerate(listing_urls, 1):
            print(f"  [{i}/{len(listing_urls)}] Scraping...", end=" ", flush=True)
            lead = await scrape_listing(page, url)
            leads.append(lead)
            print(lead.name or "(no name)")
            # Small delay to be polite
            await asyncio.sleep(1.5)

        await browser.close()

    return leads


def save_csv(leads: list[Lead], path: str) -> None:
    fields = list(Lead.__dataclass_fields__.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([asdict(l) for l in leads])
    print(f"Saved {len(leads)} leads → {path}")


def save_json(leads: list[Lead], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(l) for l in leads], f, indent=2, ensure_ascii=False)
    print(f"Saved {len(leads)} leads → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps business listings for leads.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py "plumbers in Chicago"
  python scraper.py "dentists in New York" --max 50 --format json
  python scraper.py "coffee shops London" --max 100 --output leads.csv
  python scraper.py "lawyers in Austin TX" --no-headless
        """,
    )
    parser.add_argument("query", help='Search query, e.g. "dentists in Chicago"')
    parser.add_argument("--max", type=int, default=20, help="Max results to scrape (default: 20)")
    parser.add_argument("--format", choices=["csv", "json", "both"], default="csv", help="Output format (default: csv)")
    parser.add_argument("--output", default="", help="Output file path (without extension)")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in visible mode (for debugging)")

    args = parser.parse_args()

    slug = re.sub(r"[^\w]+", "_", args.query.lower()).strip("_")
    base = args.output or f"leads_{slug}"

    leads = asyncio.run(
        search_google_maps(
            query=args.query,
            max_results=args.max,
            headless=not args.no_headless,
        )
    )

    if not leads:
        print("No leads found.")
        return

    if args.format in ("csv", "both"):
        save_csv(leads, f"{base}.csv")
    if args.format in ("json", "both"):
        save_json(leads, f"{base}.json")

    # Print a quick summary table
    print("\n--- Preview (first 5) ---")
    for lead in leads[:5]:
        print(f"  {lead.name:<35} {lead.phone:<20} {lead.address}")


if __name__ == "__main__":
    main()
