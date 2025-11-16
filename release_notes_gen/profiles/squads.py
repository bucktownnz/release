"""Squad profile loader and formatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_SQUADS_FILE = Path(__file__).resolve().with_name("squads.yaml")
_PROFILE_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_CACHE_MTIME: Optional[float] = None


def _load_profiles() -> Dict[str, Dict[str, Any]]:
    """Load and cache squad profiles from YAML."""
    global _PROFILE_CACHE, _CACHE_MTIME

    if not _SQUADS_FILE.exists():
        _PROFILE_CACHE = {}
        _CACHE_MTIME = None
        return {}

    current_mtime = _SQUADS_FILE.stat().st_mtime
    if _PROFILE_CACHE is not None and _CACHE_MTIME == current_mtime:
        return _PROFILE_CACHE

    with _SQUADS_FILE.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    normalised: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        normalised[key.strip().upper()] = value

    _PROFILE_CACHE = normalised
    _CACHE_MTIME = current_mtime
    return normalised


def load_squad_profile(name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the squad profile dict for a given name (case-insensitive)."""
    if not name:
        return None

    profiles = _load_profiles()
    return profiles.get(name.strip().upper())


def _format_list(items: Optional[Any]) -> str:
    if not isinstance(items, list) or not items:
        return "- Not specified"
    return "\n".join(f"- {str(item).strip()}" for item in items if str(item).strip())


def format_squad_context(profile: Dict[str, Any]) -> str:
    """Return a compact multi-section string describing the squad."""
    display_name = profile.get("display_name") or "Unknown Squad"
    mission = (profile.get("mission") or "").strip() or "Not specified"

    sections = [
        f"Squad: {display_name}",
        "",
        "Mission:",
        mission,
        "",
        "Primary users:",
        _format_list(profile.get("primary_users")),
        "",
        "Systems owned:",
        _format_list(profile.get("systems_owned")),
        "",
        "Responsibilities:",
        _format_list(profile.get("responsibilities")),
        "",
        "Non-functional priorities:",
        _format_list(profile.get("non_functional_priorities")),
        "",
        "Characteristics of good tickets for this squad:",
        _format_list(profile.get("good_ticket_characteristics")),
    ]

    return "\n".join(sections).strip()

