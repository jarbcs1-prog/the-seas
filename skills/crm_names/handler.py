"""
CRM names skill handler.

Port of CRM `splitName` function — parses a raw name string into
firstName, lastName, and fullName. Handles suffixes like "Jr.",
multi-word last names, and normalizes whitespace.

The repository is injectable (``set_repository`` / module-level ``_REPO``)
so tests can seed a mock without touching the global module import.
"""

from __future__ import annotations

import re
from typing import Optional

from system.capabilities import enabled, unavailable

# Capability check — gate on "crm" capability
REQUIRED_CAPABILITIES: list[str] = []

# Injectable repository (stub for interface consistency with other CRM skills)
_REPO: Optional[object] = None


def set_repository(repo: object) -> None:
    """Inject the repository used by this handler (for tests / wiring)."""
    global _REPO
    _REPO = repo


def get_repository() -> Optional[object]:
    """Return the active repository, or None if not set."""
    return _REPO


def _normalise(value: str) -> str:
    """Normalize a string: lowercase and remove non-alphanumeric characters."""
    return value.lower().replace(r"[^a-z0-9]", "")


def _split_name(full_name: str) -> dict:
    """
    Parse a full name into firstName, lastName, and fullName.

    Handles:
    - Suffixes like "Jr.", "Sr.", "II", "III", "IV"
    - Multi-word last names (e.g., "van der Berg", "de la Cruz")
    - Normalizes whitespace
    - Returns fullName as the cleaned input
    """
    # Clean the name: trim and normalize whitespace
    cleaned = full_name.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    if not cleaned:
        return {"firstName": "", "lastName": "", "fullName": ""}

    # Common suffixes to handle
    suffixes = {
        "jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v",
        "junior", "senior", "2nd", "3rd", "4th", "5th"
    }

    parts = cleaned.split(" ")

    # Check if the last part is a suffix
    suffix = ""
    if len(parts) > 1 and parts[-1].lower().rstrip(".") in suffixes:
        suffix = parts.pop()

    # First part is firstName
    first_name = parts[0] if parts else ""

    # Remaining parts (minus suffix) form the lastName
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    # If there was a suffix, append it to lastName
    if suffix:
        last_name = (last_name + " " + suffix).strip()

    return {
        "firstName": first_name,
        "lastName": last_name,
        "fullName": cleaned,
    }


def execute(query: str, **kwargs) -> dict:
    """
    Parse a raw name string into structured components.

    Args:
        query: A raw name string (e.g., "Sarah Marchetti", "John Smith Jr.",
               "Ada Lovelace", "Juan Carlos de la Cruz")

    Returns:
        A dict with:
        - ok: True if successful, False if capability not enabled
        - firstName: The parsed first name
        - lastName: The parsed last name (may include suffix)
        - fullName: The cleaned full name
        - error: Present only if ok is False
    """
    # Capability gating — check at handler entry
    for cap in REQUIRED_CAPABILITIES:
        if not enabled(cap):
            return unavailable(cap)

    if not query or not query.strip():
        return {
            "ok": True,
            "firstName": "",
            "lastName": "",
            "fullName": "",
        }

    result = _split_name(query)

    return {
        "ok": True,
        "firstName": result["firstName"],
        "lastName": result["lastName"],
        "fullName": result["fullName"],
    }