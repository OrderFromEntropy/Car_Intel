"""Tundra-specific interview: collects the variable parameters (zip, budget,
mileage ceiling) — everything else is pre-locked by the evaluation framework."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from core.models import CarProfile
from core.ollama_client import chat_complete, chat_stream, extract_json_block

log = logging.getLogger(__name__)

# Pre-locked by the framework — not asked about during the interview
_LOCKED = {
    "make": "Toyota",
    "model": "Tundra",
    "condition": "used",
    "year_min": 2014,
    "year_max": 2021,
}

_SYSTEM_PROMPT = """You are CarIntel's Tundra acquisition specialist.
The buyer is searching for a second-generation Toyota Tundra (2014–2021).
The following specs are already locked in by their evaluation framework:
  • Make/Model: Toyota Tundra (2nd gen, 2014–2021)
  • Condition: Used
  • Cab: CrewMax only
  • Engine: 5.7L V8 only
  • Drivetrain: 4x4 only
  • Tow package: Required
  • No salvage/rebuilt titles

Your job is to collect ONLY the following remaining details:
  1. ZIP code (for local search radius)
  2. Search radius in miles (default 200 for a competitive market)
  3. Maximum price budget (USD)
  4. Maximum acceptable mileage (default is open — the framework handles tier cutoffs)
  5. Preferred tier focus: Are they hunting for a Grail (S/A), a value play (B/C), or open to anything?
  6. Any specific trim preference: 1794 Edition, Limited, Platinum, SR5 — or open?
  7. Any must-have color? (Smoked Mesquite, Quicksand, Magnetic Gray, etc. — or open)
  8. Any other notes (fleet history concerns, specific packages, etc.)

Ask in a natural, efficient way — this buyer knows Tundras, so be direct and concise.
Combine questions where it makes sense. Do not ask about make, model, cab type, engine,
or drivetrain — those are already locked.

Once you have items 1–4 at minimum (zip, radius, budget, mileage), emit this block:

PROFILE_READY:
```json
{
  "make": "Toyota",
  "model": "Tundra",
  "condition": "used",
  "year_min": 2014,
  "year_max": 2021,
  "zipcode": "...",
  "radius_miles": 200,
  "price_max": null_or_int,
  "mileage_max": null_or_int,
  "trim": "...",
  "extra_notes": "..."
}
```

Do NOT emit PROFILE_READY until you have at minimum: zipcode and price_max."""

_GREETING = (
    "Let's find your Tundra. The framework is locked in — CrewMax, 5.7L V8, "
    "4x4, tow package, clean title, approved-state provenance only.\n\n"
    "What's your ZIP code and search radius, and what's the top of your budget?"
)

PROFILE_READY_MARKER = "PROFILE_READY:"


def initial_message() -> str:
    return _GREETING


def build_messages(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": _SYSTEM_PROMPT}, *history]


async def stream_reply(history: list[dict]) -> AsyncIterator[str]:
    messages = build_messages(history)
    async for token in chat_stream(messages, temperature=0.65):
        yield token


async def extract_profile(full_reply: str) -> CarProfile | None:
    """Parse a CarProfile from the assistant's PROFILE_READY block."""
    if PROFILE_READY_MARKER not in full_reply:
        return None

    after_marker = full_reply.split(PROFILE_READY_MARKER, 1)[1]
    data = extract_json_block(after_marker)

    if not data:
        log.warning("Could not parse profile JSON — requesting repair")
        repair_messages = [
            {"role": "system", "content": "You are a JSON formatter. Output only valid JSON, nothing else."},
            {
                "role": "user",
                "content": f"Extract the car search profile and return ONLY a JSON object:\n{after_marker}",
            },
        ]
        raw = await chat_complete(repair_messages, temperature=0.0, max_tokens=512)
        data = extract_json_block(raw)
        if not data:
            return None

    # Enforce locked fields regardless of what the LLM emitted
    data.update(_LOCKED)

    try:
        return CarProfile(**data)
    except Exception as exc:
        log.error("Profile validation error: %s", exc)
        return None
