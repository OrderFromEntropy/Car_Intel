"""DuckDuckGo/DDGS search aggregator for car listings.

NOTE: The duckduckgo_search package was renamed to ddgs.
Run: pip install ddgs

Query strategy (broad → specific to maximise results from Bing):
  Tier 1 — just make+model, no trim, no year → highest hit rate
  Tier 2 — add year anchor
  Tier 3 — add site name as keyword
  Tier 4 — add full trim + zip
  Tier 5 — site: operator (sometimes works)
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
_QUERY_DELAY = 1.0
_ERROR_DELAY = 2.0


def _build_queries(profile: CarProfile) -> list[str]:
    make = (profile.make or "").strip()
    model = (profile.model or "").strip()
    base = f"{make} {model}".strip()   # e.g. "Toyota Tundra"

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

    # ── Tier 1: broadest — make+model only ───────────────────────────────
    queries.append(q(base, "for sale"))                   # "Toyota Tundra for sale"
    queries.append(q(base, "used"))                        # "Toyota Tundra used"
    if zip_code:
        queries.append(q(base, "for sale", zip_code))     # + zip

    # ── Tier 2: add year ─────────────────────────────────────────────────
    if year_anchor:
        queries.append(q(year_anchor, base, "for sale"))
        if zip_code:
            queries.append(q(year_anchor, base, zip_code))

    # ── Tier 3: site name as keyword (with base only, no trim) ───────────
    for site in TARGET_SITES:
        queries.append(q(year_anchor, base, site))

    # ── Tier 4: add trim (more specific — after broad passes) ────────────
    if trim:
        queries.append(q(year_anchor, base, trim, "for sale"))
        for site in TARGET_SITES:
            queries.append(q(year_anchor, base, trim, site))

    # ── Tier 5: site: operator ───────────────────────────────────────────
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
    queries = _build_queries(profile)
    log.info("Search: %d queries for %r", len(queries), profile.to_search_summary())
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
            log.info("  %r → %d results", query[:65], len(batch))
        except Exception as exc:
            log.warning("  Query %d failed: %s", i + 1, exc)
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
    """Single DDG/DDGS text search, two attempts for version compatibility."""
    # Attempt 1: no extra kwargs (broadest compatibility)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=RESULTS_PER_QUERY))
        if results:
            return results
    except Exception as exc:
        log.debug("DDGS attempt 1 failed for %r: %s", query[:60], exc)

    # Attempt 2: explicit safesearch
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=RESULTS_PER_QUERY, safesearch="off")) or []
    except Exception as exc:
        log.debug("DDGS attempt 2 failed for %r: %s", query[:60], exc)
        return []


def listings_to_dataframe(listings: list[CarListing]) -> pd.DataFrame:
    return pd.DataFrame([l.model_dump() for l in listings])
