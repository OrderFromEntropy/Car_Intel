"""Chat interview logic: drives Gemma to collect a full CarProfile from the user."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from core.models import CarProfile
from core.ollama_client import chat_complete, chat_stream, extract_json_block

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are CarIntel's friendly car-buying assistant.
Your goal is to gather exactly these details from the user:
  1. Make (brand, e.g. Toyota)
  2. Model (e.g. Tundra)
  3. Year or year range (e.g. 2014-2021)
  4. Condition: new, used, or either
  5. Trim level or package (e.g. TRD Pro, SR5) — say "any" if they don't care
  6. Maximum price budget (USD)
  7. Maximum acceptable mileage
  8. ZIP code for local search
  9. Search radius in miles (default 100)
  10. Any other notes or must-haves (optional)

Ask naturally — one or two questions at a time. Be conversational, helpful, and brief.
Once you have collected ALL required details (1-8), end your message with this exact block:

PROFILE_READY:
```json
{
  "make": "...",
  "model": "...",
  "year_min": null_or_int,
  "year_max": null_or_int,
  "condition": "new|used|any",
  "trim": "...",
  "price_max": null_or_int,
  "mileage_max": null_or_int,
  "zipcode": "...",
  "radius_miles": 100,
  "extra_notes": "..."
}
```

Do NOT emit PROFILE_READY until you are certain you have all required fields."""

_GREETING = (
    "Hey there! I'm CarIntel's search assistant. "
    "Let's find you the perfect vehicle. What make and model are you after?"
)

PROFILE_READY_MARKER = "PROFILE_READY:"


def initial_message() -> str:
    return _GREETING


def build_messages(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": _SYSTEM_PROMPT}, *history]


async def stream_reply(history: list[dict]) -> AsyncIterator[str]:
    messages = build_messages(history)
    async for token in chat_stream(messages, temperature=0.7):
        yield token


async def extract_profile(full_reply: str) -> CarProfile | None:
    """Try to parse a CarProfile from the assistant's PROFILE_READY block."""
    if PROFILE_READY_MARKER not in full_reply:
        return None

    after_marker = full_reply.split(PROFILE_READY_MARKER, 1)[1]
    data = extract_json_block(after_marker)
    if not data:
        # Ask Gemma to re-emit the JSON cleanly
        log.warning("Could not parse profile JSON; requesting clean re-emission")
        repair_messages = [
            {"role": "system", "content": "You are a JSON formatter. Output only valid JSON."},
            {
                "role": "user",
                "content": (
                    f"Extract the car search profile from this text and return ONLY a JSON object:\n{after_marker}"
                ),
            },
        ]
        raw = await chat_complete(repair_messages, temperature=0.0, max_tokens=512)
        data = extract_json_block(raw)
        if not data:
            return None

    try:
        return CarProfile(**data)
    except Exception as exc:
        log.error("Profile validation error: %s", exc)
        return None
