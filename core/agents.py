"""LLM Agent pipeline: Ranker (Agent 1) and Summarizer (Agent 2).

Ranker uses the full Tundra Evaluation Framework:
  Step 1 — Global mandatory checks
  Step 2 — F-tier hard disqualifiers
  Step 3 — State provenance
  Step 4 — Tier assignment (S/A/B/C/D/F)
  Step 5 — Color scoring modifiers
  Step 6 — Structured JSON output with disqualifiers + flags + reasoning
"""

from __future__ import annotations

import asyncio
import logging

from core.models import CarListing, CarProfile, TIERS
from core.ollama_client import chat_complete, extract_json_block
from core.tundra_framework import build_ranker_system_prompt, build_summarizer_context

log = logging.getLogger(__name__)

_RANKER_SYSTEM = build_ranker_system_prompt()

_SUMMARIZER_SYSTEM = """You are a concise automotive analyst writing buyer briefs for second-generation
Toyota Tundra listings. Be factual and specific. No filler phrases. Maximum 3 sentences."""

_TIER_LABELS = {
    "S": "Grail Truck",
    "A": "Strong Buy",
    "B": "Solid Deal",
    "C": "Proceed Carefully",
    "D": "High-Risk Buy",
    "F": "Do Not Purchase",
}

_BATCH_SIZE = 8  # smaller batches keep the context tight for the detailed rubric


async def rank_listings(
    listings: list[CarListing],
    profile: CarProfile,
    progress_callback=None,
) -> list[CarListing]:
    """Agent 1: Run the Tundra evaluation framework on every listing."""

    ranked: list[CarListing] = list(listings)
    batches = [ranked[i : i + _BATCH_SIZE] for i in range(0, len(ranked), _BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        snippets = []
        for i, listing in enumerate(batch):
            snippets.append(
                f"[{i}] title={listing.title!r}\n"
                f"    price={listing.price!r}  mileage={listing.mileage!r}  "
                f"source={listing.source!r}\n"
                f"    snippet={listing.snippet[:300]!r}"
            )

        prompt = (
            f"Buyer ZIP: {profile.zipcode or 'not specified'} | "
            f"Budget: {f'${profile.price_max:,}' if profile.price_max else 'open'} | "
            f"Max mileage: {f'{profile.mileage_max:,} mi' if profile.mileage_max else 'open'}\n\n"
            f"Apply the Tundra Evaluation Framework to each listing below.\n\n"
            + "\n\n".join(snippets)
        )

        messages = [
            {"role": "system", "content": _RANKER_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await chat_complete(messages, temperature=0.05, max_tokens=1024)
            data = extract_json_block(raw)
            rankings = data.get("rankings", [])
            for entry in rankings:
                idx = entry.get("index")
                if idx is None or not (0 <= idx < len(batch)):
                    continue
                tier = str(entry.get("tier", "F")).upper()
                if tier not in TIERS:
                    tier = "F"
                batch[idx].tier = tier
                batch[idx].disqualifiers = [str(d) for d in entry.get("disqualifiers", [])]
                batch[idx].flags = [str(f) for f in entry.get("flags", [])]
                batch[idx].tier_reasoning = str(entry.get("tier_reasoning", ""))
        except Exception as exc:
            log.error("Ranker batch %d failed: %s", batch_idx, exc)
            for listing in batch:
                if not listing.tier:
                    listing.tier = "F"
                    listing.disqualifiers = ["Ranking error — manual review required"]

        if progress_callback:
            progress_callback(batch_idx + 1, len(batches))

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
    """Agent 2: Generate tier-aware 2-3 sentence summaries for the top N listings."""

    tier_order = {t: i for i, t in enumerate(TIERS)}
    sorted_listings = sorted(listings, key=lambda l: tier_order.get(l.tier, len(TIERS)))
    to_summarise = sorted_listings[:top_n]

    async def _summarise_one(listing: CarListing, idx: int) -> None:
        tier_context = build_summarizer_context(listing.tier)
        disq_note = ""
        if listing.disqualifiers:
            disq_note = f"\nDisqualifiers found: {'; '.join(listing.disqualifiers)}"
        flag_note = ""
        if listing.flags:
            flag_note = f"\nFlags: {'; '.join(listing.flags)}"

        prompt = (
            f"Listing #{idx + 1}:\n"
            f"Title: {listing.title}\n"
            f"Price: {listing.price}  |  Mileage: {listing.mileage}  |  Source: {listing.source}\n"
            f"Details: {listing.snippet}\n"
            f"Assigned tier: {listing.tier} — {tier_label(listing.tier)}\n"
            f"Reasoning: {listing.tier_reasoning}"
            f"{disq_note}{flag_note}\n\n"
            f"Writing guidance: {tier_context}\n\n"
            f"Write the 2-3 sentence buyer brief now."
        )
        messages = [
            {"role": "system", "content": _SUMMARIZER_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        try:
            summary = await chat_complete(messages, temperature=0.4, max_tokens=160)
            listing.summary = summary.strip()
        except Exception as exc:
            log.error("Summarizer failed for listing %d: %s", idx, exc)
            listing.summary = listing.snippet[:200]

        if progress_callback:
            progress_callback(idx)

    sem = asyncio.Semaphore(3)

    async def _guarded(listing: CarListing, idx: int) -> None:
        async with sem:
            await _summarise_one(listing, idx)

    await asyncio.gather(*[_guarded(l, i) for i, l in enumerate(to_summarise)])
    return listings


def tier_label(tier: str) -> str:
    return _TIER_LABELS.get(tier, tier)
