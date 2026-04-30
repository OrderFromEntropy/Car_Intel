"""DuckDuckGo search aggregator targeting car listing sites."""

from __future__ import annotations

import asyncio
import logging
from typing import Generator

import pandas as pd
from duckduckgo_search import DDGS

from core.models import CarListing, CarProfile

log = logging.getLogger(__name__)

TARGET_SITES = ["cars.com", "carfax.com", "autotrader.com"]
RESULTS_PER_QUERY = 20
MAX_TOTAL = 50


def _build_queries(profile: CarProfile) -> list[str]:
    base = f"{profile.make} {profile.model}".strip()
    if profile.trim:
        base = f"{base} {profile.trim}"

    year_part = ""
    if profile.year_min and profile.year_max:
        year_part = f"{profile.year_min}-{profile.year_max}"
    elif profile.year_min:
        year_part = str(profile.year_min)
    elif profile.year_max:
        year_part = str(profile.year_max)

    price_part = f"under ${profile.price_max:,}" if profile.price_max else ""
    location_part = f"near {profile.zipcode}" if profile.zipcode else ""

    queries = []
    for site in TARGET_SITES:
        q_parts = [f"site:{site}"]
        if year_part:
            q_parts.append(year_part)
        q_parts.append(base)
        if profile.condition != "any":
            q_parts.append(profile.condition)
        if price_part:
            q_parts.append(price_part)
        if location_part:
            q_parts.append(location_part)
        queries.append(" ".join(q_parts))

    # Also one broad query without site: restriction for diversity
    broad = " ".join(filter(None, [year_part, base, "for sale", price_part, location_part]))
    queries.append(broad)

    return queries


def _dedupe(listings: list[CarListing]) -> list[CarListing]:
    seen_urls: set[str] = set()
    unique: list[CarListing] = []
    for l in listings:
        if l.url and l.url not in seen_urls:
            seen_urls.add(l.url)
            unique.append(l)
    return unique


async def run_search(profile: CarProfile) -> list[CarListing]:
    """Execute all queries concurrently and return up to MAX_TOTAL unique listings."""
    queries = _build_queries(profile)
    log.info("Running %d search queries", len(queries))

    async def _query(q: str) -> list[CarListing]:
        try:
            results = await asyncio.to_thread(_ddg_search, q)
            return [CarListing.from_ddg_result(r) for r in results]
        except Exception as exc:
            log.warning("Search query failed: %s — %s", q, exc)
            return []

    tasks = [_query(q) for q in queries]
    batches = await asyncio.gather(*tasks)

    all_listings: list[CarListing] = []
    for batch in batches:
        all_listings.extend(batch)

    unique = _dedupe(all_listings)
    log.info("Found %d unique listings before capping", len(unique))
    return unique[:MAX_TOTAL]


def _ddg_search(query: str) -> list[dict]:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=RESULTS_PER_QUERY))
    return results


def listings_to_dataframe(listings: list[CarListing]) -> pd.DataFrame:
    rows = [l.model_dump() for l in listings]
    return pd.DataFrame(rows)
