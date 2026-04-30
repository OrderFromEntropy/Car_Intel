"""Thin async wrapper around the Ollama library with retry logic."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator

import ollama

log = logging.getLogger(__name__)

MODEL = "gemma4:e2b"
_RETRY_DELAYS = (2, 4, 8, 16)  # seconds


async def chat_stream(messages: list[dict], *, temperature: float = 0.7) -> AsyncIterator[str]:
    """Stream tokens from Gemma; yields partial text chunks."""
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=MODEL,
                messages=messages,
                stream=True,
                options={"temperature": temperature},
            )
            for chunk in response:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
            return
        except Exception as exc:
            if delay is None:
                log.error("Ollama chat_stream failed after all retries: %s", exc)
                raise
            log.warning("Ollama attempt %d failed (%s). Retrying in %ds…", attempt, exc, delay)
            await asyncio.sleep(delay)


async def chat_complete(messages: list[dict], *, temperature: float = 0.3, max_tokens: int = 2048) -> str:
    """Non-streaming chat completion; returns full response string."""
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=MODEL,
                messages=messages,
                stream=False,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
            return response.get("message", {}).get("content", "")
        except Exception as exc:
            if delay is None:
                log.error("Ollama chat_complete failed after all retries: %s", exc)
                raise
            log.warning("Ollama attempt %d failed (%s). Retrying in %ds…", attempt, exc, delay)
            await asyncio.sleep(delay)
    return ""


def extract_json_block(text: str) -> dict:
    """Parse the first JSON object found in an LLM response."""
    # Try fenced code block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        m = re.search(r"(\{[^{}]*\})", text, re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Light repair: trailing commas
        raw_clean = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(raw_clean)
        except json.JSONDecodeError:
            return {}
