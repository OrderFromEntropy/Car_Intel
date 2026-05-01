"""DuckDuckGo search aggregator for car listings.

Query strategy:
  - Primary: very broad queries (just vehicle name + "for sale") — reliable on DDG
  - Secondary: site-name-as-keyword queries for targeted results
  - Tertiary: site: operator (inconsistent but occasionally works)
  - Sequential with delay to avoid rate limiting
  - Per-query status callbacks for visible UI feedback
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

import pandas as pd
from duckduckgo_search import DDGS

from core.models import CarListing, CarProfile

log = logging.getLogger(__name__)

TARGET_SITES = ["autotrader.com", "cars.com", "carfax.com"]
RESULTS_PER_QUERY = 10   # lower = faster, less likely to time out
MAX_TOTAL = 50
_QUERY_DELAY = 1.0        # seconds between queries
_ERROR_DELAY = 2.0


def _build_queries(profile: CarProfile) -> list[str]:
    make = profile.make.strip()
    model = profile.model.strip()
    base = f"{make} {model}"

    # Trim: only add if it's a real value
    trim = (profile.trim or "").strip()
    if trim.lower() in ("", "any", "open"):
        trim = ""
    full_base = f"{base} {trim}".strip() if trim else base

    # Year: pick the midpoint year or single year as primary anchor
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

    # Tier 1: broadest possible — highest DDG hit rate
    queries.append(q(base, "for sale"))
    queries.append(q(base, "used for sale"))
    if zip_code:
        queries.append(q(full_base, "for sale", zip_code))

    # Tier 2: with year anchor
    if year_anchor:
        queries.append(q(year_anchor, base, "for sale"))
        queries.append(q(year_anchor, full_base, "used"))

    # Tier 3: site-name as keyword (more reliable than site: operator)
    for site in TARGET_SITES:
        queries.append(q(year_anchor, full_base, site))

    # Tier 4: site: operator (may return 0 but worth trying)
    for site in TARGET_SITES:
        if zip_code:
            queries.append(q(f"site:{site}", year_anchor, base, zip_code))
        else:
            queries.append(q(f"site:{site}", year_anchor, base))

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
    """Run queries sequentially and return up to MAX_TOTAL unique listings."""
    queries = _build_queries(profile)
    log.info("Search starting: %d queries for %r", len(queries), profile.to_search_summary())
    all_listings: list[CarListing] = []

    for i, query in enumerate(queries):
        n_unique = len(_dedupe(all_listings))
        msg = f"Search {i + 1}/{len(queries)} — {n_unique} found so far…"
        log.info(msg)
        if status_cb:
            status_cb(msg)

        try:
            raw = await asyncio.to_thread(_ddg_search, query)
            batch = [CarListing.from_ddg_result(r) for r in raw]
            all_listings.extend(batch)
            log.info("  Query %r → %d raw results", query[:60], len(batch))
        except Exception as exc:
            log.warning("  Query %d failed: %s — %r", i + 1, exc, query)
            await asyncio.sleep(_ERROR_DELAY)
            continue

        if len(_dedupe(all_listings)) >= MAX_TOTAL:
            log.info("Reached %d unique — stopping early", MAX_TOTAL)
            break

        await asyncio.sleep(_QUERY_DELAY)

    unique = _dedupe(all_listings)
    log.info("Search complete: %d unique listings", len(unique))
    return unique[:MAX_TOTAL]


def _ddg_search(query: str) -> list[dict]:
    """Synchronous DDG search. Tries without safesearch first, then with."""
    # Attempt 1: no safesearch kwarg (most compatible across DDGS versions)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=RESULTS_PER_QUERY))
        if results:
            return results
    except Exception as exc:
        log.warning("DDGS attempt 1 failed for %r: %s", query[:60], exc)

    # Attempt 2: with explicit safesearch off
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=RESULTS_PER_QUERY, safesearch="off"))
        return results or []
    except Exception as exc:
        log.warning("DDGS attempt 2 failed for %r: %s", query[:60], exc)
        return []


def listings_to_dataframe(listings: list[CarListing]) -> pd.DataFrame:
    return pd.DataFrame([l.model_dump() for l in listings])
