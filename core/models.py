"""Pydantic data models for CarIntel."""

from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, field_validator


TIERS = ["S", "A", "B", "C", "D", "F"]


class CarProfile(BaseModel):
    """Structured search profile extracted from the interview conversation."""

    make: str = ""
    model: str = ""
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    mileage_max: Optional[int] = None
    condition: str = "used"  # "new" | "used" | "any"
    trim: str = ""
    zipcode: str = ""
    radius_miles: int = 100
    extra_notes: str = ""

    @field_validator("condition", mode="before")
    @classmethod
    def normalise_condition(cls, v: str) -> str:
        v = v.lower().strip()
        if v in ("new", "used", "any"):
            return v
        return "used"

    def is_complete(self) -> bool:
        return bool(self.make and self.model and self.zipcode)

    def to_search_summary(self) -> str:
        parts = []
        if self.condition != "any":
            parts.append(self.condition)
        year_str = ""
        if self.year_min and self.year_max:
            year_str = f"{self.year_min}-{self.year_max}"
        elif self.year_min:
            year_str = f"{self.year_min}+"
        elif self.year_max:
            year_str = f"up to {self.year_max}"
        if year_str:
            parts.append(year_str)
        parts.append(f"{self.make} {self.model}".strip())
        if self.trim:
            parts.append(self.trim)
        if self.price_max:
            parts.append(f"under ${self.price_max:,}")
        if self.mileage_max:
            parts.append(f"under {self.mileage_max:,} miles")
        if self.zipcode:
            parts.append(f"near {self.zipcode}")
        return " ".join(parts)


class CarListing(BaseModel):
    """A single car listing retrieved from search."""

    title: str
    url: str
    snippet: str
    source: str = ""
    price: str = ""
    mileage: str = ""
    tier: str = ""
    summary: str = ""
    rank_score: int = 0
    # Tundra evaluation results
    disqualifiers: list[str] = []
    flags: list[str] = []
    tier_reasoning: str = ""

    @classmethod
    def from_ddg_result(cls, result: dict) -> "CarListing":
        title = result.get("title", "")
        url = result.get("href", result.get("link", ""))
        snippet = result.get("body", result.get("snippet", ""))

        _DOMAIN_LABELS = {
            "cars.com": "cars.com",
            "autotrader.com": "autotrader.com",
            "carfax.com": "carfax.com",
            "cargurus.com": "cargurus.com",
            "truecar.com": "truecar.com",
            "edmunds.com": "edmunds.com",
            "craigslist.org": "craigslist",
            "facebook.com": "fb marketplace",
            "marketplace.facebook.com": "fb marketplace",
        }
        source = ""
        for domain, label in _DOMAIN_LABELS.items():
            if domain in url:
                source = label
                break

        price = _extract_price(title + " " + snippet)
        mileage = _extract_mileage(title + " " + snippet)

        return cls(
            title=title,
            url=url,
            snippet=snippet[:500],
            source=source,
            price=price,
            mileage=mileage,
        )


def _extract_price(text: str) -> str:
    patterns = [
        r"\$[\d,]+(?:\.\d{2})?",
        r"(?:price|asking)[:\s]+\$?[\d,]+",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = re.sub(r"[^\d]", "", m.group())
            if raw and 1000 <= int(raw) <= 500000:
                return f"${int(raw):,}"
    return ""


def _extract_mileage(text: str) -> str:
    m = re.search(r"([\d,]+)\s*(?:mi(?:les?)?|k\s*miles?)", text, re.IGNORECASE)
    if m:
        raw = re.sub(r"[^\d]", "", m.group(1))
        if raw:
            val = int(raw)
            if val < 1000:
                val *= 1000
            if val < 500000:
                return f"{val:,} mi"
    return ""
