"""
CRM deals skill handler.

Port of CRM `dealsForContact` tool — returns all deals attached to a contact.
Uses the CRM repository interface so it works with both the mock and a real backend.

The repository is injectable (``set_repository`` / module-level ``_REPO``)
so tests can seed a mock without touching the global module import.
"""

from __future__ import annotations

from typing import Optional

from system.crm_repository import CrmRepository, MockCrmRepository
from system.capabilities import enabled, unavailable

# Capability check — this skill uses the CRM repository but no external
# API keys directly; the repository may use keys indirectly.  We check
# for the CRM researcher profile's capabilities as a proxy.
REQUIRED_CAPABILITIES: list[str] = []

# Injectable repository.  Defaults to a fresh MockCrmRepository; tests (and
# the executor) may call ``set_repository`` to supply a seeded instance.
_REPO: Optional[CrmRepository] = None


def set_repository(repo: CrmRepository) -> None:
    """Inject the repository used by this handler (for tests / wiring)."""
    global _REPO
    _REPO = repo


def get_repository() -> CrmRepository:
    """Return the active repository, creating a mock by default."""
    global _REPO
    if _REPO is None:
        _REPO = MockCrmRepository()
    return _REPO


def execute(contact_id: str) -> dict:
    """
    Get all deals for a contact.

    Args:
        contact_id: The CRM contact ID to look up deals for.

    Returns:
        A dict with:
        - ok: True if successful, False if capability not enabled
        - deals: list of deal dicts (empty if none found)
        - error: present only if ok is False
    """
    # Capability gating — check at handler entry
    for cap in REQUIRED_CAPABILITIES:
        if not enabled(cap):
            return unavailable(cap)

    repo: CrmRepository = get_repository()
    deals = repo.deals_for_contact(contact_id)

    return {
        "ok": True,
        "deals": deals,
    }