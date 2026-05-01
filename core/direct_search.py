"""Direct HTTP scrapers for individual car listing URLs.

Cars.com  — parses HTML search results for /vehicledetail/ links.
AutoTrader — calls the unofficial JSON REST API for listing IDs.
Craigslist — parses HTML for individual post links.

These bypass the problem where DDG/Bing only returns search-category
pages (e.g. carfax.com/cars-for-sale/toyota/tundra) instead of the
individual listing pages the ranker needs.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from core.models import CarListing, CarProfile

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_JSON_HEADERS = {
    **_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

_TIMEOUT = 15
_DELAY = 0.8  # seconds between requests to same domain


# ── cars.com ─────────────────────────────────────────────────────────────────

def _cars_com_url(profile: CarProfile, page: int = 1) -> str:
    params: dict[str, str | int] = {
        "makes[]": (profile.make or "toyota").lower(),
        "models[]": f"{(profile.make or 'toyota').lower()}-{(profile.model or '').lower()}",
        "list_price_max": profile.price_max or "",
        "list_price_min": profile.price_min or "",
        "maximum_distance": profile.radius_miles or 500,
        "mileage_max": profile.mileage_max or "",
        "stock_type": "used",
        "zip": profile.zipcode or "",
        "page": page,
    }
    if profile.year_min:
        params["year_min"] = profile.year_min
    if profile.year_max:
        params["year_max"] = profile.year_max
    # remove empty
    params = {k: v for k, v in params.items() if v != "" and v is not None}
    return f"https://www.cars.com/shopping/results/?{urlencode(params)}"


def _scrape_cars_com_page(url: str) -> list[CarListing]:
    """Fetch one page of cars.com search results and extract individual listings."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("cars.com fetch failed: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    listings: list[CarListing] = []

    # Individual listing links contain /vehicledetail/
    seen: set[str] = set()
    for tag in soup.find_all("a", href=re.compile(r"/vehicledetail/")):
        href = tag.get("href", "")
        full_url = urljoin("https://www.cars.com", href)
        # strip query params for dedup
        base_url = full_url.split("?")[0]
        if base_url in seen:
            continue
        seen.add(base_url)

        # Try to extract title/price from parent article or nearby text
        article = tag.find_parent("article") or tag.find_parent("div")
        title = ""
        price = ""
        mileage = ""
        snippet = ""

        if article:
            h2 = article.find(["h2", "h3"])
            if h2:
                title = h2.get_text(strip=True)

            price_el = article.find(class_=re.compile(r"price", re.I))
            if price_el:
                m = re.search(r"\$?([\d,]+)", price_el.get_text())
                if m:
                    try:
                        price = f"${int(m.group(1).replace(',', '')):,}"
                    except ValueError:
                        pass

            mileage_el = article.find(string=re.compile(r"\d[\d,]+ mi", re.I))
            if mileage_el:
                m = re.search(r"([\d,]+)\s*mi", str(mileage_el), re.I)
                if m:
                    try:
                        mileage = f"{int(m.group(1).replace(',', '')):,} mi"
                    except ValueError:
                        pass

            snippet = article.get_text(" ", strip=True)[:200]

        if not title:
            title = tag.get_text(strip=True) or "Car listing"

        listings.append(
            CarListing(
                title=title,
                url=base_url,
                snippet=snippet,
                source="cars.com",
                price=price or "",
                mileage=mileage or "",
            )
        )

    log.info("cars.com page → %d listings  (%s)", len(listings), url[:80])
    return listings


def scrape_cars_dot_com(
    profile: CarProfile,
    max_pages: int = 3,
    status_cb: Callable[[str], None] | None = None,
) -> list[CarListing]:
    all_listings: list[CarListing] = []
    for page in range(1, max_pages + 1):
        if status_cb:
            status_cb(f"cars.com page {page}/{max_pages}…")
        url = _cars_com_url(profile, page)
        batch = _scrape_cars_com_page(url)
        all_listings.extend(batch)
        if not batch:
            break
        time.sleep(_DELAY)
    return all_listings


# ── AutoTrader unofficial JSON API ───────────────────────────────────────────

def _autotrader_api_url(profile: CarProfile, first_record: int = 0) -> str:
    make = (profile.make or "TOYOTA").upper()
    model = (profile.model or "TUNDRA").upper()

    params: dict[str, str | int] = {
        "zip": profile.zipcode or "90001",
        "makeCodeList": make,
        "modelCodeList": f"{make}_{model}",
        "searchRadius": profile.radius_miles or 500,
        "isNewSearch": "true",
        "numRecords": 25,
        "firstRecord": first_record,
        "listingType": "USED",
        "sortBy": "relevance",
        "pixelWidth": 1200,
        "channel": "ATC",
        "largeImage": "false",
    }
    if profile.price_max:
        params["maxPrice"] = profile.price_max
    if profile.price_min:
        params["minPrice"] = profile.price_min
    if profile.year_min:
        params["startYear"] = profile.year_min
    if profile.year_max:
        params["endYear"] = profile.year_max
    if profile.mileage_max:
        params["maxMileage"] = profile.mileage_max

    return f"https://www.autotrader.com/rest/lsc/listing?{urlencode(params)}"


def _parse_autotrader_json(data: dict) -> list[CarListing]:
    listings_raw = data.get("listings", [])
    listings: list[CarListing] = []
    for item in listings_raw:
        lid = item.get("id") or item.get("listingId")
        if not lid:
            continue
        url = f"https://www.autotrader.com/cars-for-sale/vehicledetails.xhtml?listingId={lid}"

        title_parts = [
            str(item.get("year", "")),
            item.get("make", ""),
            item.get("model", ""),
            item.get("trim", ""),
        ]
        title = " ".join(p for p in title_parts if p).strip()
        if not title:
            title = item.get("heading", "Car listing")

        price_info = item.get("pricingDetail", {}) or {}
        raw_price = price_info.get("salePrice") or price_info.get("price")
        price = ""
        if raw_price:
            m = re.search(r"([\d,]+)", str(raw_price))
            if m:
                try:
                    price = f"${int(m.group(1).replace(',', '')):,}"
                except ValueError:
                    pass

        raw_mileage = item.get("mileage")
        mileage = ""
        if raw_mileage:
            m = re.search(r"([\d,]+)", str(raw_mileage))
            if m:
                try:
                    mileage = f"{int(m.group(1).replace(',', '')):,} mi"
                except ValueError:
                    pass

        snippet_parts = [
            item.get("color", ""),
            item.get("interiorColor", ""),
            item.get("transmission", ""),
            item.get("engineSize", ""),
            item.get("drivetype", ""),
        ]
        snippet = " | ".join(p for p in snippet_parts if p)

        dealer = item.get("dealerInfo", {}) or {}
        city = dealer.get("city", "")
        state = dealer.get("state", "")
        if city or state:
            snippet += f" — {city}, {state}".strip(", —").strip()

        listings.append(
            CarListing(
                title=title,
                url=url,
                snippet=snippet,
                source="autotrader.com",
                price=price,
                mileage=mileage,
            )
        )
    return listings


def scrape_autotrader_api(
    profile: CarProfile,
    max_pages: int = 2,
    status_cb: Callable[[str], None] | None = None,
) -> list[CarListing]:
    all_listings: list[CarListing] = []
    for page in range(max_pages):
        first_record = page * 25
        if status_cb:
            status_cb(f"AutoTrader records {first_record}–{first_record + 24}…")
        url = _autotrader_api_url(profile, first_record)
        try:
            resp = requests.get(url, headers=_JSON_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("AutoTrader API failed (page %d): %s", page, exc)
            break

        batch = _parse_autotrader_json(data)
        all_listings.extend(batch)
        log.info("AutoTrader page %d → %d listings", page + 1, len(batch))
        if not batch:
            break
        time.sleep(_DELAY)

    return all_listings


# ── Craigslist ────────────────────────────────────────────────────────────────

def _craigslist_url(profile: CarProfile) -> str:
    """Build a Craigslist national cars+trucks search URL."""
    params: dict[str, str | int] = {
        "query": f"{profile.make or ''} {profile.model or ''}".strip(),
        "srchType": "T",
        "hasPic": 1,
        "auto_make_model": f"{profile.make or ''} {profile.model or ''}".strip(),
    }
    if profile.price_max:
        params["max_price"] = profile.price_max
    if profile.price_min:
        params["min_price"] = profile.price_min
    if profile.year_min:
        params["min_auto_year"] = profile.year_min
    if profile.year_max:
        params["max_auto_year"] = profile.year_max
    if profile.mileage_max:
        params["auto_miles_max"] = profile.mileage_max
    return f"https://www.craigslist.org/search/cta?{urlencode(params)}"


def scrape_craigslist(
    profile: CarProfile,
    status_cb: Callable[[str], None] | None = None,
) -> list[CarListing]:
    if status_cb:
        status_cb("Craigslist national search…")
    url = _craigslist_url(profile)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("Craigslist fetch failed: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    listings: list[CarListing] = []
    seen: set[str] = set()

    for tag in soup.select("a.cl-app-anchor[href]"):
        href = tag.get("href", "")
        # Individual CL posts match /d/..../XXXXXXXXX.html
        if not re.search(r"/d/.+/\d+\.html$", href):
            continue
        full_url = href if href.startswith("http") else urljoin("https://www.craigslist.org", href)
        if full_url in seen:
            continue
        seen.add(full_url)

        title_el = tag.find(class_=re.compile(r"title", re.I)) or tag
        title = title_el.get_text(strip=True)

        price = ""
        price_el = tag.find_parent().find(class_=re.compile(r"price", re.I)) if tag.find_parent() else None
        if price_el:
            m = re.search(r"\$?([\d,]+)", price_el.get_text())
            if m:
                try:
                    price = f"${int(m.group(1).replace(',', '')):,}"
                except ValueError:
                    pass

        listings.append(
            CarListing(
                title=title or "Craigslist listing",
                url=full_url,
                snippet="",
                source="craigslist",
                price=price,
            )
        )

    log.info("Craigslist → %d individual listings", len(listings))
    return listings


# ── Orchestrator ─────────────────────────────────────────────────────────────

async def run_direct_search(
    profile: CarProfile,
    status_cb: Callable[[str], None] | None = None,
) -> list[CarListing]:
    """Run all direct scrapers concurrently and return deduplicated results."""

    def _cars_com():
        return scrape_cars_dot_com(profile, max_pages=3, status_cb=status_cb)

    def _autotrader():
        return scrape_autotrader_api(profile, max_pages=2, status_cb=status_cb)

    def _craigslist():
        return scrape_craigslist(profile, status_cb=status_cb)

    results = await asyncio.gather(
        asyncio.to_thread(_cars_com),
        asyncio.to_thread(_autotrader),
        asyncio.to_thread(_craigslist),
        return_exceptions=True,
    )

    combined: list[CarListing] = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("Direct scraper raised: %s", r)
        elif isinstance(r, list):
            combined.extend(r)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[CarListing] = []
    for listing in combined:
        if listing.url and listing.url not in seen:
            seen.add(listing.url)
            unique.append(listing)

    log.info("Direct search complete: %d unique listings", len(unique))
    return unique
