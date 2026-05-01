"""DuckDuckGo search aggregator for car listings.

Query strategy:
  - Primary: broad queries using the site name as a keyword (reliable)
  - Secondary: site: operator queries (sometimes work, zero-result safe)
  - Sequential execution with delays to avoid DDG rate limiting
"""

from __future__ import annotations

import asyncio
import logging

import pandas as pd
from duckduckgo_search import DDGS

from core.models import CarListing, CarProfile

log = logging.getLogger(__name__)

# These sites are used as search keywords AND for result source tagging
TARGET_SITES = ["cars.com", "autotrader.com", "carfax.com"]

# Broader acceptance — tag any recognisable listing domain
_LISTING_DOMAINS = [
    "cars.com", "autotrader.com", "carfax.com",
    "cargurus.com", "truecar.com", "edmunds.com",
    "craigslist.org", "facebook.com/marketplace",
    "marketplace.facebook.com", "offerups.com",
]

RESULTS_PER_QUERY = 15
MAX_TOTAL = 50
_QUERY_DELAY = 0.8   # seconds between DDG calls to stay under rate limit
_ERROR_DELAY = 2.0


def _build_queries(profile: CarProfile) -> list[str]:
    base = f"{profile.make} {profile.model}".strip()
    if profile.trim:
        base = f"{base} {profile.trim}"

    year_str = ""
    if profile.year_min and profile.year_max:
        if profile.year_min == profile.year_max:
            year_str = str(profile.year_min)
        else:
            year_str = f"{profile.year_min} {profile.year_max}"
    elif profile.year_min:
        year_str = str(profile.year_min)
    elif profile.year_max:
        year_str = str(profile.year_max)

    location = f"near {profile.zipcode}" if profile.zipcode else ""

    def q(*parts) -> str:
        return " ".join(p for p in parts if p).strip()

    queries = []

    # ── Primary: broad, no site: operator ────────────────────────────
    # General listing search
    queries.append(q(year_str, base, "for sale used", location))

    # One query per target site (site name as keyword, not operator)
    for site in TARGET_SITES:
        queries.append(q(year_str, base, "for sale", site, location))

    # Alternative phrasing for diversity
    queries.append(q("buy used", year_str, base, location))
    queries.append(q(year_str, base, "listing price", location))

    # ── Secondary: site: operator (works inconsistently, 0-result safe) ──
    for site in TARGET_SITES:
        site_q = f"site:{site}"
        if profile.zipcode:
            queries.append(q(site_q, year_str, base, profile.zipcode))
        else:
            queries.append(q(site_q, year_str, base))

    return [x for x in queries if x]


def _dedupe(listings: list[CarListing]) -> list[CarListing]:
    seen: set[str] = set()
    out: list[CarListing] = []
    for l in listings:
        if l.url and l.url not in seen:
            seen.add(l.url)
            out.append(l)
    return out


async def run_search(profile: CarProfile) -> list[CarListing]:
    """Run queries sequentially (rate-limit safe) and return up to MAX_TOTAL unique listings."""
    queries = _build_queries(profile)
    log.info("Running %d queries sequentially", len(queries))

    all_listings: list[CarListing] = []

    for i, query in enumerate(queries):
        try:
            results = await asyncio.to_thread(_ddg_search, query)
            batch = [CarListing.from_ddg_result(r) for r in results]
            all_listings.extend(batch)
            log.info("Query %d/%d %r → %d results", i + 1, len(queries), query, len(batch))
        except Exception as exc:
            log.warning("Query %d failed (%s): %r", i + 1, exc, query)
            await asyncio.sleep(_ERROR_DELAY)
            continue

        # Stop early once we have enough unique hits
        if len(_dedupe(all_listings)) >= MAX_TOTAL:
            log.info("Reached %d unique listings — stopping early", MAX_TOTAL)
            break

        await asyncio.sleep(_QUERY_DELAY)

    unique = _dedupe(all_listings)
    log.info("Total unique listings: %d", len(unique))
    return unique[:MAX_TOTAL]


def _ddg_search(query: str) -> list[dict]:
    """Run a single DDG text search. Returns empty list on any error."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=RESULTS_PER_QUERY, safesearch="off"))
    except Exception as exc:
        log.warning("DDGS error for %r: %s", query, exc)
        return []


def listings_to_dataframe(listings: list[CarListing]) -> pd.DataFrame:
    return pd.DataFrame([l.model_dump() for l in listings])
