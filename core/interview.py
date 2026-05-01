"""Interview logic — adapts to the active user profile's framework and defaults."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator

from core.models import CarProfile
from core.ollama_client import chat_complete, chat_stream, extract_json_block

if TYPE_CHECKING:
    from core.profile_manager import UserProfile

log = logging.getLogger(__name__)

PROFILE_READY_MARKER = "PROFILE_READY:"

# ── Tundra specialist prompt ──────────────────────────────────────────────────

_TUNDRA_SYSTEM = """You are CarIntel's Tundra acquisition specialist.
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
  2. Search radius in miles (default 200 — competitive market)
  3. Maximum price budget (USD)
  4. Maximum acceptable mileage (framework handles tier cutoffs)
  5. Preferred tier focus: Grail (S/A), value play (B/C), or open to all?
  6. Trim preference: 1794 Edition, Limited, Platinum, SR5, or open?
  7. Color preference: Smoked Mesquite, Quicksand, Magnetic Gray, etc. — or open?
  8. Any other notes (fleet history concerns, packages, etc.)

This buyer knows Tundras — be direct and efficient. Combine questions where sensible.
Do NOT ask about make, model, cab, engine, or drivetrain — those are locked.
{defaults_note}

Once you have items 1–3 at minimum, emit:

PROFILE_READY:
```json
{{
  "make": "Toyota",
  "model": "Tundra",
  "condition": "used",
  "year_min": 2014,
  "year_max": 2021,
  "zipcode": "...",
  "radius_miles": 200,
  "price_max": null,
  "mileage_max": null,
  "trim": "...",
  "extra_notes": "..."
}}
```

Do NOT emit PROFILE_READY until you have at minimum: zipcode and price_max."""

_TUNDRA_LOCKED = {
    "make": "Toyota",
    "model": "Tundra",
    "condition": "used",
    "year_min": 2014,
    "year_max": 2021,
}

_TUNDRA_GREETING = (
    "Let's find your Tundra. The framework is locked in — CrewMax, 5.7L V8, "
    "4x4, tow package, clean title, approved-state provenance only.\n\n"
    "What's your ZIP code and search radius, and what's your budget ceiling?"
)

# ── Generic prompt ────────────────────────────────────────────────────────────

_GENERIC_SYSTEM = """You are CarIntel's friendly car-buying assistant.
Your goal is to gather exactly these details from the user:
  1. Make (brand, e.g. Ford, Toyota)
  2. Model (e.g. F-150, Camry)
  3. Year or year range (e.g. 2018-2023)
  4. Condition: new, used, or either
  5. Trim level or package — say "any" if they don't care
  6. Maximum price budget (USD)
  7. Maximum acceptable mileage
  8. ZIP code for local search
  9. Search radius in miles (default 100)
  10. Any other notes or must-haves (optional)

Ask naturally — one or two questions at a time. Be conversational, helpful, and brief.
{defaults_note}

Once you have all required details (1-8), end your message with:

PROFILE_READY:
```json
{{
  "make": "...",
  "model": "...",
  "year_min": null,
  "year_max": null,
  "condition": "used",
  "trim": "...",
  "price_max": null,
  "mileage_max": null,
  "zipcode": "...",
  "radius_miles": 100,
  "extra_notes": "..."
}}
```

Do NOT emit PROFILE_READY until you have all required fields."""

_GENERIC_GREETING = (
    "Hey there! I'm CarIntel's search assistant. "
    "Let's find you the perfect vehicle. What make and model are you after?"
)


# ── Public API ────────────────────────────────────────────────────────────────

def initial_message(user_profile: "UserProfile | None" = None) -> str:
    if user_profile and user_profile.framework == "tundra":
        return _TUNDRA_GREETING
    return _GENERIC_GREETING


def build_messages(
    history: list[dict],
    user_profile: "UserProfile | None" = None,
) -> list[dict]:
    system = _build_system_prompt(user_profile)
    return [{"role": "system", "content": system}, *history]


async def stream_reply(
    history: list[dict],
    user_profile: "UserProfile | None" = None,
) -> AsyncIterator[str]:
    messages = build_messages(history, user_profile)
    async for token in chat_stream(messages, temperature=0.65):
        yield token


async def extract_profile(
    full_reply: str,
    user_profile: "UserProfile | None" = None,
) -> CarProfile | None:
    """Parse a CarProfile from the PROFILE_READY block, then merge locked/default fields."""
    if PROFILE_READY_MARKER not in full_reply:
        return None

    after_marker = full_reply.split(PROFILE_READY_MARKER, 1)[1]
    data = extract_json_block(after_marker)

    if not data:
        log.warning("Could not parse profile JSON — requesting repair")
        repair = [
            {"role": "system", "content": "Output only valid JSON, nothing else."},
            {"role": "user", "content": f"Extract the car profile as JSON:\n{after_marker}"},
        ]
        raw = await chat_complete(repair, temperature=0.0, max_tokens=512)
        data = extract_json_block(raw)
        if not data:
            return None

    # Merge: profile defaults → collected data (collected data wins for non-locked fields)
    if user_profile:
        merged = dict(user_profile.defaults)
        merged.update({k: v for k, v in data.items() if v is not None and v != ""})
        data = merged

    # Re-enforce locked fields for tundra (LLM cannot override these)
    if user_profile and user_profile.framework == "tundra":
        data.update(_TUNDRA_LOCKED)

    try:
        return CarProfile(**data)
    except Exception as exc:
        log.error("Profile validation error: %s", exc)
        return None


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_system_prompt(user_profile: "UserProfile | None") -> str:
    defaults_note = _build_defaults_note(user_profile)
    if user_profile and user_profile.framework == "tundra":
        return _TUNDRA_SYSTEM.format(defaults_note=defaults_note)
    return _GENERIC_SYSTEM.format(defaults_note=defaults_note)


def _build_defaults_note(user_profile: "UserProfile | None") -> str:
    if not user_profile or not user_profile.defaults:
        return ""
    d = user_profile.defaults
    known = []
    field_labels = {
        "make": "Make", "model": "Model", "year_min": "Year from",
        "year_max": "Year to", "price_max": "Budget", "mileage_max": "Max mileage",
        "zipcode": "ZIP", "radius_miles": "Radius", "trim": "Trim",
    }
    for key, label in field_labels.items():
        val = d.get(key)
        if val:
            if key == "price_max":
                known.append(f"{label}: ${val:,}")
            elif key == "mileage_max":
                known.append(f"{label}: {val:,} mi")
            else:
                known.append(f"{label}: {val}")
    if not known:
        return ""
    return (
        "\nAlready known from saved profile (skip these or just confirm):\n"
        + "\n".join(f"  • {item}" for item in known)
    )
