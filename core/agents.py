"""LLM Agent pipeline: Ranker (Agent 1) and Summarizer (Agent 2)."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from core.models import CarListing, CarProfile, TIERS
from core.ollama_client import chat_complete, extract_json_block

log = logging.getLogger(__name__)

_RANKER_SYSTEM = """You are an expert automotive analyst and car-buying advisor.
Your job is to rank car listings against a buyer's ideal profile.
Respond ONLY with a valid JSON object — no prose, no markdown fences outside the JSON."""

_SUMMARIZER_SYSTEM = """You are a concise automotive copywriter.
Write a 2-3 sentence summary of a car listing that highlights its value, condition, and location.
Be factual, specific, and persuasive. No filler phrases."""

_TIER_LABELS = {
    "S": "Best Match",
    "A": "Great Deal",
    "B": "Good Option",
    "C": "Consider",
    "D": "Below Average",
    "F": "Poor Match",
}

_BATCH_SIZE = 10  # listings per ranker call to avoid context overflow


async def rank_listings(
    listings: list[CarListing],
    profile: CarProfile,
    progress_callback=None,
) -> list[CarListing]:
    """Agent 1: Assign a tier (S/A/B/C/D/F) to each listing."""

    ranked: list[CarListing] = list(listings)
    batches = [ranked[i : i + _BATCH_SIZE] for i in range(0, len(ranked), _BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        snippets = []
        for i, listing in enumerate(batch):
            snippets.append(
                f"{i}: title={listing.title!r} price={listing.price!r} "
                f"mileage={listing.mileage!r} source={listing.source!r} "
                f"snippet={listing.snippet[:200]!r}"
            )

        prompt = (
            f"Buyer profile: {profile.to_search_summary()}\n\n"
            f"Rate each listing below against this profile. "
            f"Return a JSON object with a single key 'rankings' containing a list of objects, "
            f"each with 'index' (int) and 'tier' (one of S, A, B, C, D, F).\n\n"
            + "\n".join(snippets)
        )

        messages = [
            {"role": "system", "content": _RANKER_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await chat_complete(messages, temperature=0.1, max_tokens=512)
            data = extract_json_block(raw)
            rankings = data.get("rankings", [])
            for entry in rankings:
                idx = entry.get("index")
                tier = str(entry.get("tier", "F")).upper()
                if tier not in TIERS:
                    tier = "F"
                if idx is not None and 0 <= idx < len(batch):
                    batch[idx].tier = tier
        except Exception as exc:
            log.error("Ranker batch %d failed: %s", batch_idx, exc)
            for listing in batch:
                if not listing.tier:
                    listing.tier = "F"

        if progress_callback:
            progress_callback(batch_idx + 1, len(batches))

    # Fill any un-ranked listings
    for listing in ranked:
        if not listing.tier:
            listing.tier = "F"

    return ranked


async def summarize_listings(
    listings: list[CarListing],
    profile: CarProfile,
    top_n: int = 20,
    progress_callback=None,
) -> list[CarListing]:
    """Agent 2: Generate 2-3 sentence summaries for the top N listings."""

    # Sort by tier, then summarise top_n
    tier_order = {t: i for i, t in enumerate(TIERS)}
    sorted_listings = sorted(listings, key=lambda l: tier_order.get(l.tier, len(TIERS)))
    to_summarise = sorted_listings[:top_n]

    async def _summarise_one(listing: CarListing, idx: int) -> None:
        prompt = (
            f"Buyer wants: {profile.to_search_summary()}\n\n"
            f"Listing:\nTitle: {listing.title}\nPrice: {listing.price}\n"
            f"Mileage: {listing.mileage}\nSource: {listing.source}\n"
            f"Details: {listing.snippet}\n\n"
            f"Write a 2-3 sentence summary."
        )
        messages = [
            {"role": "system", "content": _SUMMARIZER_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        try:
            summary = await chat_complete(messages, temperature=0.5, max_tokens=150)
            listing.summary = summary.strip()
        except Exception as exc:
            log.error("Summarizer failed for listing %d: %s", idx, exc)
            listing.summary = listing.snippet[:200]
        if progress_callback:
            progress_callback(idx)

    # Summarise concurrently in small batches to avoid hammering Ollama
    sem = asyncio.Semaphore(3)

    async def _guarded(listing: CarListing, idx: int) -> None:
        async with sem:
            await _summarise_one(listing, idx)

    tasks = [_guarded(listing, i) for i, listing in enumerate(to_summarise)]
    await asyncio.gather(*tasks)

    return listings


def tier_label(tier: str) -> str:
    return _TIER_LABELS.get(tier, tier)
