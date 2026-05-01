"""User profile management — persisted to ~/.carintel/profiles/."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_PROFILES_DIR = Path.home() / ".carintel" / "profiles"
_SETTINGS_FILE = Path.home() / ".carintel" / "settings.json"

# Built-in evaluation framework names → display labels
BUILTIN_FRAMEWORKS: dict[str, str] = {
    "generic": "Generic (any vehicle)",
    "tundra": "Tundra Evaluation Framework (2nd Gen, 2014–2021)",
}


class UserProfile(BaseModel):
    """A named search profile with vehicle defaults and an evaluation framework."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    display_name: str
    framework: str = "generic"          # key from BUILTIN_FRAMEWORKS
    # Pre-filled CarProfile fields — any key here skips that interview question
    defaults: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_used: str = ""

    def framework_label(self) -> str:
        return BUILTIN_FRAMEWORKS.get(self.framework, self.framework)

    def summary_line(self) -> str:
        d = self.defaults
        parts = []
        if d.get("make") and d.get("model"):
            parts.append(f"{d['make']} {d['model']}")
        if d.get("year_min") or d.get("year_max"):
            y_min = d.get("year_min", "")
            y_max = d.get("year_max", "")
            if y_min and y_max:
                parts.append(f"{y_min}–{y_max}")
            elif y_min:
                parts.append(f"{y_min}+")
        if d.get("price_max"):
            parts.append(f"≤${d['price_max']:,}")
        if d.get("zipcode"):
            parts.append(f"ZIP {d['zipcode']}")
        return "  ·  ".join(parts) if parts else "No defaults set"


class ProfileManager:
    """Static helpers for profile CRUD on disk."""

    @staticmethod
    def _ensure_dirs() -> None:
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def list_profiles() -> list[UserProfile]:
        ProfileManager._ensure_dirs()
        profiles = []
        for path in sorted(_PROFILES_DIR.glob("*.json")):
            try:
                profiles.append(UserProfile.model_validate_json(path.read_text()))
            except Exception as exc:
                log.warning("Skipping malformed profile %s: %s", path.name, exc)
        return profiles

    @staticmethod
    def load(profile_id: str) -> Optional[UserProfile]:
        path = _PROFILES_DIR / f"{profile_id}.json"
        if not path.exists():
            return None
        try:
            return UserProfile.model_validate_json(path.read_text())
        except Exception as exc:
            log.error("Failed to load profile %s: %s", profile_id, exc)
            return None

    @staticmethod
    def save(profile: UserProfile) -> None:
        ProfileManager._ensure_dirs()
        path = _PROFILES_DIR / f"{profile.id}.json"
        path.write_text(profile.model_dump_json(indent=2))
        log.info("Saved profile: %s (%s)", profile.display_name, profile.id)

    @staticmethod
    def delete(profile_id: str) -> None:
        path = _PROFILES_DIR / f"{profile_id}.json"
        if path.exists():
            path.unlink()
            log.info("Deleted profile: %s", profile_id)

    @staticmethod
    def get_active_id() -> str:
        if _SETTINGS_FILE.exists():
            try:
                data = json.loads(_SETTINGS_FILE.read_text())
                return data.get("active_profile_id", "")
            except Exception:
                pass
        return ""

    @staticmethod
    def set_active_id(profile_id: str) -> None:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if _SETTINGS_FILE.exists():
            try:
                data = json.loads(_SETTINGS_FILE.read_text())
            except Exception:
                pass
        data["active_profile_id"] = profile_id
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2))

    @staticmethod
    def get_active_profile() -> Optional[UserProfile]:
        active_id = ProfileManager.get_active_id()
        if active_id:
            profile = ProfileManager.load(active_id)
            if profile:
                return profile
        # Fall back to first available profile
        profiles = ProfileManager.list_profiles()
        if profiles:
            return profiles[0]
        return None

    @staticmethod
    def ensure_defaults_exist() -> None:
        """Create the built-in Tundra profile and a Generic profile on first run."""
        if ProfileManager.list_profiles():
            return

        tundra = UserProfile(
            display_name="My Tundra Hunt",
            framework="tundra",
            defaults={
                "make": "Toyota",
                "model": "Tundra",
                "condition": "used",
                "year_min": 2014,
                "year_max": 2021,
            },
        )
        generic = UserProfile(
            display_name="New Search",
            framework="generic",
            defaults={},
        )
        ProfileManager.save(tundra)
        ProfileManager.save(generic)
        ProfileManager.set_active_id(tundra.id)
        log.info("Created default profiles (Tundra + Generic)")
