"""Search aggregator: direct scrapers first, DDGS as supplement.

Direct scrapers (cars.com HTML, AutoTrader JSON API, Craigslist HTML) give
individual listing URLs and structured data.  DDG/Bing is used to top up
the result set if direct scrapers return fewer than MIN_DIRECT results.

NOTE: The duckduckgo_search package was renamed to ddgs.
Run: pip install ddgs
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import pandas as pd

# Support both the renamed package (ddgs) and the old one
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # type: ignore

from core.direct_search import run_direct_search
from core.models import CarListing, CarProfile

log = logging.getLogger(__name__)

TARGET_SITES = ["autotrader.com", "cars.com", "carfax.com"]

_LISTING_DOMAINS = {
    "cars.com": "cars.com",
    "autotrader.com": "autotrader.com",
    "carfax.com": "carfax.com",
    "cargurus.com": "cargurus.com",
    "truecar.com": "truecar.com",
    "edmunds.com": "edmunds.com",
    "craigslist.org": "craigslist",
    "facebook.com": "fb marketplace",
}

RESULTS_PER_QUERY = 15
MAX_TOTAL = 50
MIN_DIRECT = 10   # if direct scrapers get this many, skip most DDG queries
_QUERY_DELAY = 1.0
_ERROR_DELAY = 2.0

# Patterns that identify individual listings vs search/category pages
_INDIVIDUAL_LISTING_PATTERNS = [
    "/vehicledetail/",        # cars.com individual listing
    "vehicledetails.xhtml",   # autotrader individual listing
    "/vehicle/",
    "/listing/",
    "/cars-for-sale/details",
    "/used-",                 # carfax individual
    r"\d{7,}",                # 7+ digit ID typically means individual listing
]


def _looks_like_individual_listing(url: str) -> bool:
    import re
    for pat in _INDIVIDUAL_LISTING_PATTERNS:
        if re.search(pat, url):
            return True
    return False


def _build_queries(profile: CarProfile) -> list[str]:
    make = (profile.make or "").strip()
    model = (profile.model or "").strip()
    base = f"{make} {model}".strip()

    trim = (profile.trim or "").strip()
    if trim.lower() in ("", "any", "open", "none"):
        trim = ""

    year_anchor = ""
    if profile.year_min and profile.year_max:
        year_anchor = str((profile.year_min + profile.year_max) // 2)
    elif profile.year_min:
        year_anchor = str(profile.year_min)
    elif profile.year_max:
        year_anchor = str(profile.year_max)

    zip_code = (profile.zipcode or "").strip()

    def q(*parts: str) -> str:
        return " ".join(p for p in parts if p).strip()

    queries: list[str] = []

    # Tier 1: broadest — make+model only
    queries.append(q(base, "for sale"))
    queries.append(q(base, "used"))
    if zip_code:
        queries.append(q(base, "for sale", zip_code))

    # Tier 2: add year
    if year_anchor:
        queries.append(q(year_anchor, base, "for sale"))
        if zip_code:
            queries.append(q(year_anchor, base, zip_code))

    # Tier 3: site name as keyword (with base only, no trim)
    for site in TARGET_SITES:
        queries.append(q(year_anchor, base, site))

    # Tier 4: add trim
    if trim:
        queries.append(q(year_anchor, base, trim, "for sale"))
        for site in TARGET_SITES:
            queries.append(q(year_anchor, base, trim, site))

    # Tier 5: site: operator
    for site in TARGET_SITES:
        queries.append(q(f"site:{site}", year_anchor, base, zip_code))

    return [x for x in queries if x]


def _dedupe(listings: list[CarListing]) -> list[CarListing]:
    seen: set[str] = set()
    out: list[CarListing] = []
    for listing in listings:
        if listing.url and listing.url not in seen:
            seen.add(listing.url)
            out.append(listing)
    return out


async def run_search(
    profile: CarProfile,
    status_cb: Callable[[str], None] | None = None,
) -> list[CarListing]:
    # ── Phase 1: direct scrapers ──────────────────────────────────────────
    if status_cb:
        status_cb("Fetching direct listings from cars.com, AutoTrader, Craigslist…")
    try:
        direct_listings = await run_direct_search(profile, status_cb=status_cb)
    except Exception as exc:
        log.warning("Direct search failed entirely: %s", exc)
        direct_listings = []

    n_direct = len(direct_listings)
    log.info("Direct scrapers: %d listings", n_direct)
    if status_cb:
        status_cb(f"Direct search: {n_direct} individual listings found.")

    all_listings = list(direct_listings)

    # ── Phase 2: DDG supplement if direct search was thin ────────────────
    if n_direct < MIN_DIRECT:
        queries = _build_queries(profile)
        log.info("Direct results thin (%d) — running %d DDG queries", n_direct, len(queries))

        for i, query in enumerate(queries):
            n_unique = len(_dedupe(all_listings))
            msg = f"DDG search {i + 1}/{len(queries)} — {n_unique} total so far…"
            log.info(msg)
            if status_cb:
                status_cb(msg)

            try:
                raw = await asyncio.to_thread(_ddg_search, query)
                # Only keep results that look like individual listing URLs
                batch = [
                    CarListing.from_ddg_result(r)
                    for r in raw
                    if _looks_like_individual_listing(r.get("href", "") or r.get("url", ""))
                ]
                if not batch:
                    # Fall back to all DDG results if none look like individual listings
                    batch = [CarListing.from_ddg_result(r) for r in raw]
                all_listings.extend(batch)
                log.info("  %r → %d results (%d individual)", query[:65], len(raw), len(batch))
            except Exception as exc:
                log.warning("  DDG query %d failed: %s", i + 1, exc)
                await asyncio.sleep(_ERROR_DELAY)
                continue

            if len(_dedupe(all_listings)) >= MAX_TOTAL:
                log.info("Reached %d unique — stopping early", MAX_TOTAL)
                break

            await asyncio.sleep(_QUERY_DELAY)

    unique = _dedupe(all_listings)

    # Sort: individual listings first (cars.com/autotrader direct results), then DDG
    individual = [l for l in unique if l.source in ("cars.com", "autotrader.com", "craigslist")]
    supplement = [l for l in unique if l not in individual]
    ordered = individual + supplement

    log.info("Search complete: %d unique (%d direct, %d DDG)", len(ordered), len(individual), len(supplement))
    return ordered[:MAX_TOTAL]


def _ddg_search(query: str) -> list[dict]:
    """Single DDG/DDGS text search, two attempts for version compatibility."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=RESULTS_PER_QUERY))
        if results:
            return results
    except Exception as exc:
        log.debug("DDGS attempt 1 failed for %r: %s", query[:60], exc)

    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=RESULTS_PER_QUERY, safesearch="off")) or []
    except Exception as exc:
        log.debug("DDGS attempt 2 failed for %r: %s", query[:60], exc)
        return []


def listings_to_dataframe(listings: list[CarListing]) -> pd.DataFrame:
    return pd.DataFrame([l.model_dump() for l in listings])
