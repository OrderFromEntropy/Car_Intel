"""LLM Agent pipeline: Ranker (Agent 1) and Summarizer (Agent 2).

framework="tundra"  → full 6-step Tundra Evaluation Framework
framework="generic" → standard best-match ranking against buyer profile
"""

from __future__ import annotations

import asyncio
import logging

from core.models import CarListing, CarProfile, TIERS
from core.ollama_client import chat_complete, extract_json_block
from core.tundra_framework import build_ranker_system_prompt, build_summarizer_context

log = logging.getLogger(__name__)

_TUNDRA_RANKER_SYSTEM = build_ranker_system_prompt()

_GENERIC_RANKER_SYSTEM = """You are an expert automotive analyst and car-buying advisor.
Your job is to rank car listings against a buyer's stated profile.

Evaluation pipeline (apply in order):
  1. Basic fit: does the listing match the buyer's make, model, year, trim?
  2. Price check: is the price within the buyer's budget?
  3. Mileage check: is mileage within acceptable range?
  4. Quality signals: number of owners, title type, service history if mentioned.
  5. Location: does provenance / distance look reasonable?

Tier definitions:
  S — Best possible match. Hits every criterion, may be below market value.
  A — Strong buy. Meets most criteria, good value.
  B — Solid option. Minor gaps (mileage slightly high, or price at ceiling). Worth a PPI.
  C — Proceed carefully. Notable gaps; negotiate hard or walk if PPI fails.
  D — High-risk. Significant concerns; purchaseable only at steep discount with full inspection.
  F — Do not purchase. Fails core requirements (wrong vehicle, over budget, clear red flags).

Return ONLY a JSON object:
{
  "rankings": [
    {
      "index": 0,
      "tier": "A",
      "disqualifiers": [],
      "flags": ["Service history not mentioned — request records"],
      "tier_reasoning": "2019, clean title, priced at market, under mileage budget"
    }
  ]
}

Rules for uncertain data: never upgrade a tier due to missing info — flag it instead."""

_GENERIC_SUMMARIZER_SYSTEM = """You are a concise automotive copywriter writing 2-3 sentence
buyer briefs. Be factual, specific, and highlight value. No filler phrases."""

_TUNDRA_SUMMARIZER_SYSTEM = """You are a concise automotive analyst writing buyer briefs for
second-generation Toyota Tundra listings. Be factual and specific. No filler phrases. Max 3 sentences."""

_TIER_LABELS = {
    "S": "Grail Truck",
    "A": "Strong Buy",
    "B": "Solid Deal",
    "C": "Proceed Carefully",
    "D": "High-Risk Buy",
    "F": "Do Not Purchase",
}

_GENERIC_TIER_LABELS = {
    "S": "Best Match",
    "A": "Great Deal",
    "B": "Good Option",
    "C": "Consider",
    "D": "Below Average",
    "F": "Poor Match",
}

_BATCH_SIZE = 8


async def rank_listings(
    listings: list[CarListing],
    profile: CarProfile,
    framework: str = "generic",
    progress_callback=None,
) -> list[CarListing]:
    """Agent 1: Rank listings using the specified evaluation framework."""

    system = _TUNDRA_RANKER_SYSTEM if framework == "tundra" else _GENERIC_RANKER_SYSTEM
    ranked = list(listings)
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
            f"Max mileage: {f'{profile.mileage_max:,} mi' if profile.mileage_max else 'open'}\n"
            f"Vehicle: {profile.make} {profile.model} {profile.trim or ''}\n\n"
            f"Evaluate each listing below.\n\n"
            + "\n\n".join(snippets)
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await chat_complete(messages, temperature=0.05, max_tokens=1024)
            data = extract_json_block(raw)
            for entry in data.get("rankings", []):
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
    framework: str = "generic",
    top_n: int = 20,
    progress_callback=None,
) -> list[CarListing]:
    """Agent 2: Generate tier-aware summaries for the top N listings."""

    use_tundra = framework == "tundra"
    system = _TUNDRA_SUMMARIZER_SYSTEM if use_tundra else _GENERIC_SUMMARIZER_SYSTEM

    tier_order = {t: i for i, t in enumerate(TIERS)}
    sorted_listings = sorted(listings, key=lambda l: tier_order.get(l.tier, len(TIERS)))
    to_summarise = sorted_listings[:top_n]

    async def _summarise_one(listing: CarListing, idx: int) -> None:
        tier_context = (
            build_summarizer_context(listing.tier)
            if use_tundra
            else f"Tier {listing.tier} listing. Be factual and highlight value."
        )
        disq_note = f"\nDisqualifiers: {'; '.join(listing.disqualifiers)}" if listing.disqualifiers else ""
        flag_note = f"\nFlags: {'; '.join(listing.flags)}" if listing.flags else ""

        prompt = (
            f"Title: {listing.title}\n"
            f"Price: {listing.price}  |  Mileage: {listing.mileage}  |  Source: {listing.source}\n"
            f"Details: {listing.snippet}\n"
            f"Tier: {listing.tier} — {tier_label(listing.tier, framework)}\n"
            f"Reasoning: {listing.tier_reasoning}"
            f"{disq_note}{flag_note}\n\n"
            f"Guidance: {tier_context}\n\nWrite the 2-3 sentence buyer brief."
        )
        messages = [
            {"role": "system", "content": system},
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


def tier_label(tier: str, framework: str = "generic") -> str:
    if framework == "tundra":
        return _TIER_LABELS.get(tier, tier)
    return _GENERIC_TIER_LABELS.get(tier, tier)
