"""
Google Maps Lead Scraper
Scrapes business listings from Google Maps for a given search query.
Extracts: name, phone, address, website, rating, review count, category, hours.

Optimized for service-area businesses (contractors, insulation, plumbing, etc.)
"""

import asyncio
import csv
import json
import re
import sys
import argparse
import urllib.parse
from dataclasses import dataclass, asdict
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext


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


# ---------------------------------------------------------------------------
# Stealth helpers – reduce bot-detection signals
# ---------------------------------------------------------------------------

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = { runtime: {} };
"""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


async def apply_stealth(context: BrowserContext) -> None:
    """Inject stealth scripts into every new page."""
    await context.add_init_script(STEALTH_JS)


# ---------------------------------------------------------------------------
# Detail extraction – uses proven XPath/CSS selectors from working scrapers
# ---------------------------------------------------------------------------

async def _safe_text(page: Page, selector: str, timeout: int = 3000) -> str:
    """Return inner text of first match, or '' if not found."""
    try:
        el = page.locator(selector).first
        return (await el.inner_text(timeout=timeout)).strip()
    except Exception:
        return ""


async def _safe_attr(page: Page, selector: str, attr: str, timeout: int = 3000) -> str:
    """Return attribute of first match, or '' if not found."""
    try:
        el = page.locator(selector).first
        val = await el.get_attribute(attr, timeout=timeout)
        return (val or "").strip()
    except Exception:
        return ""


async def scrape_listing(page: Page, url: str) -> Lead:
    """Navigate to a single listing and extract all lead fields."""
    lead = Lead(maps_url=url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        # Wait for the detail panel to render
        try:
            await page.wait_for_selector("h1.DUwDvf", timeout=8000)
        except Exception:
            await page.wait_for_timeout(3000)

        # ── Business name ──
        lead.name = await _safe_text(page, "h1.DUwDvf")
        if not lead.name:
            lead.name = await _safe_text(page, "h1")

        # ── Rating (aria-hidden span shows "4.5" etc.) ──
        rating_text = await _safe_text(page, "div.F7nice span[aria-hidden='true']")
        if not rating_text:
            rating_text = await _safe_text(page, "span.ceNzKf span[aria-hidden='true']")
        if not rating_text:
            # Fallback: parse from aria-label like "4.5 stars"
            stars_label = await _safe_attr(page, '[aria-label*="stars"]', "aria-label")
            if stars_label:
                rating_text = stars_label
        if rating_text:
            m = re.search(r"[\d.]+", rating_text)
            if m:
                lead.rating = m.group(0)

        # ── Reviews count ──
        reviews_text = await _safe_text(page, "div.F7nice span[aria-label]")
        if not reviews_text:
            reviews_text = await _safe_attr(page, "div.F7nice span[aria-label]", "aria-label")
        if not reviews_text:
            # Fallback: aria-label with "reviews" keyword
            reviews_text = await _safe_attr(page, '[aria-label*="reviews"]', "aria-label")
        if reviews_text:
            m = re.search(r"([\d,]+)", reviews_text)
            if m:
                lead.reviews = m.group(1).replace(",", "")

        # ── Category ──
        lead.category = await _safe_text(page, "button[jsaction*='category']")
        if not lead.category:
            lead.category = await _safe_text(page, "span.DkEaL")

        # ── Address ──
        # Primary: data-item-id="address"
        addr = await _safe_text(
            page,
            'button[data-item-id="address"] div.fontBodyMedium',
        )
        if not addr:
            # Fallback 1: aria-label on the data-item-id button
            addr = await _safe_attr(page, 'button[data-item-id="address"]', "aria-label")
            if addr:
                addr = addr.replace("Address: ", "")
        if not addr:
            # Fallback 2: aria-label pattern matching (most resilient)
            addr = await _safe_attr(page, '[aria-label*="Address"]', "aria-label")
            if addr:
                addr = re.sub(r"^Address:\s*", "", addr)
        lead.address = addr

        # ── Phone ──
        # Primary: data-item-id starts with "phone:tel:"
        phone = await _safe_text(
            page,
            'button[data-item-id^="phone:tel:"] div.fontBodyMedium',
        )
        if not phone:
            # Fallback 1: aria-label on the data-item-id button
            phone = await _safe_attr(
                page, 'button[data-item-id^="phone:tel:"]', "aria-label"
            )
            if phone:
                phone = phone.replace("Phone: ", "")
        if not phone:
            # Fallback 2: aria-label pattern matching
            phone = await _safe_attr(page, '[aria-label*="Phone"]', "aria-label")
            if phone:
                phone = re.sub(r"^Phone:\s*", "", phone)
        lead.phone = phone

        # ── Website ──
        # Primary: data-item-id="authority" href
        href = await _safe_attr(page, 'a[data-item-id="authority"]', "href")
        if not href:
            # Fallback 1: text inside the website element
            href = await _safe_text(
                page, 'a[data-item-id="authority"] div.fontBodyMedium'
            )
        if not href:
            # Fallback 2: aria-label pattern matching
            web_label = await _safe_attr(page, '[aria-label*="Website"]', "aria-label")
            if web_label:
                href = re.sub(r"^Website:\s*", "", web_label)
        lead.website = href

        # ── Hours ──
        # Primary: data-item-id "oh" = opening hours
        hours = await _safe_text(
            page,
            'button[data-item-id^="oh"] div.fontBodyMedium',
        )
        if not hours:
            # Fallback: aria-label pattern
            hours = await _safe_attr(page, '[aria-label*="Hours"]', "aria-label")
            if hours:
                hours = re.sub(r"^Hours:\s*", "", hours)
        # Clean up unicode characters that sometimes appear
        lead.hours = hours.replace("\u202f", " ").replace("\u2009", " ")

    except Exception as e:
        print(f"  [warn] Error scraping listing: {e}", file=sys.stderr)

    return lead


# ---------------------------------------------------------------------------
# Search & scroll the results feed
# ---------------------------------------------------------------------------

async def scroll_feed(page: Page, max_results: int) -> list[str]:
    """Scroll the Google Maps results feed and collect listing URLs."""
    listing_urls: list[str] = []
    seen: set[str] = set()

    feed = page.locator('div[role="feed"]')
    # Fallback if role="feed" not found
    try:
        await feed.wait_for(timeout=5000)
    except Exception:
        feed = page.locator("div.m6QErb")

    max_scroll_attempts = max_results * 4
    stale_rounds = 0

    for attempt in range(max_scroll_attempts):
        # Gather all place links currently in the DOM
        links = await page.locator('a[href*="/maps/place/"]').all()
        prev_count = len(listing_urls)

        for link in links:
            try:
                href = await link.get_attribute("href")
            except Exception:
                continue
            if href and href not in seen and "/maps/place/" in href:
                listing_urls.append(href)
                seen.add(href)
                if len(listing_urls) >= max_results:
                    return listing_urls[:max_results]

        # Detect end of list
        end = await page.locator("text=You've reached the end of the list").count()
        if end > 0:
            break

        # Detect no results
        no_results = await page.locator("text=No results found").count()
        if no_results > 0:
            break

        # Stale detection: if no new links after 3 consecutive scrolls, stop
        if len(listing_urls) == prev_count:
            stale_rounds += 1
            if stale_rounds >= 5:
                break
        else:
            stale_rounds = 0

        # Scroll the feed
        try:
            await feed.evaluate("el => el.scrollTop = el.scrollHeight")
        except Exception:
            await page.keyboard.press("End")
        await page.wait_for_timeout(1800)

    return listing_urls[:max_results]


async def search_google_maps(
    query: str,
    max_results: int,
    headless: bool,
) -> list[Lead]:
    """Run the full scrape: search → scroll → extract each listing."""
    leads: list[Lead] = []
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://www.google.com/maps/search/{encoded}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/Chicago",
            geolocation=None,
            permissions=[],
        )
        await apply_stealth(context)
        page = await context.new_page()

        print(f"[*] Searching: {query}")
        print(f"    URL: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # ── Dismiss consent / cookie banners ──
        for btn_text in ["Accept all", "Reject all", "I agree"]:
            try:
                btn = page.locator(f'button:has-text("{btn_text}")').first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        # ── Scroll and collect listing URLs ──
        print(f"[*] Scrolling feed to collect up to {max_results} listings...")
        listing_urls = await scroll_feed(page, max_results)
        print(f"[*] Found {len(listing_urls)} listings. Scraping details...\n")

        if not listing_urls:
            print("[!] No listings found. Try a different search query.", file=sys.stderr)
            await browser.close()
            return leads

        # ── Scrape each listing ──
        for i, url in enumerate(listing_urls, 1):
            pct = int(i / len(listing_urls) * 100)
            print(f"  [{i}/{len(listing_urls)}] ({pct}%) ", end="", flush=True)

            lead = await scrape_listing(page, url)
            leads.append(lead)

            status = lead.name or "(no name)"
            phone_tag = f" | {lead.phone}" if lead.phone else ""
            print(f"{status}{phone_tag}")

            # Polite delay between requests
            await asyncio.sleep(1.5)

        await browser.close()

    # Summary
    with_phone = sum(1 for l in leads if l.phone)
    with_website = sum(1 for l in leads if l.website)
    print(f"\n[*] Done! {len(leads)} leads scraped.")
    print(f"    With phone: {with_phone}/{len(leads)}")
    print(f"    With website: {with_website}/{len(leads)}")

    return leads


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_csv(leads: list[Lead], path: str) -> None:
    fields = list(Lead.__dataclass_fields__.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([asdict(lead) for lead in leads])
    print(f"[*] Saved CSV → {path}")


def save_json(leads: list[Lead], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(lead) for lead in leads], f, indent=2, ensure_ascii=False)
    print(f"[*] Saved JSON → {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps for business leads.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py "home insulation companies in Dallas TX"
  python scraper.py "insulation contractors near me" --max 50 --format both
  python scraper.py "spray foam insulation Chicago" --max 100 --output chicago_insulation
  python scraper.py "attic insulation Austin TX" --no-headless
  python scraper.py "plumbers in Miami" --max 30 --format json
        """,
    )
    parser.add_argument(
        "query",
        help='Search query, e.g. "home insulation companies in Dallas TX"',
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20,
        help="Maximum number of results to scrape (default: 20)",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json", "both"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Base output filename (without extension)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window (useful for debugging)",
    )

    args = parser.parse_args()

    # Build output filename from query if not specified
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
        print("[!] No leads found.")
        return

    # Save outputs
    if args.format in ("csv", "both"):
        save_csv(leads, f"{base}.csv")
    if args.format in ("json", "both"):
        save_json(leads, f"{base}.json")

    # Preview table
    print(f"\n{'─' * 90}")
    print(f"{'Name':<35} {'Phone':<18} {'Rating':>6}  Address")
    print(f"{'─' * 90}")
    for lead in leads[:10]:
        name = (lead.name[:32] + "...") if len(lead.name) > 35 else lead.name
        rating = f"{lead.rating}/5" if lead.rating else "  –  "
        print(f"  {name:<35} {lead.phone:<18} {rating:>6}  {lead.address[:40]}")
    if len(leads) > 10:
        print(f"  ... and {len(leads) - 10} more")
    print(f"{'─' * 90}")


if __name__ == "__main__":
    main()
