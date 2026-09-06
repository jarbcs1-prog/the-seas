"""
CRM search skill handler.

Port of CRM `search_crm` tool — finds contacts, companies, and deals
by name, email, domain, or deal name.  Uses the CRM repository interface
so it works with both the mock and a real backend.

The repository is injectable (``set_repository`` / module-level ``_REPO``)
so tests can seed a mock without touching the global module import.
"""

from __future__ import annotations

from typing import Optional

from system.crm_repository import CrmRepository, MockCrmRepository, SearchResult
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


def execute(
    query: str,
    kinds: Optional[list[str]] = None,
    limit: int = 10,
) -> dict:
    """
    Search the CRM for contacts, companies, and deals.

    Args:
        query: A name, email address, domain, or deal name. Minimum 2 chars.
        kinds: Narrow to ['contact'], ['company'], ['deal'], or combinations.
                Defaults to all three.
        limit: Maximum results to return (1-25, default 10).

    Returns:
        A dict with:
        - query: the search term used
        - contacts: list of contact hits
        - companies: list of company hits
        - deals: list of deal hits
        - total: total matches
        - note: guidance when zero or multiple results
    """
    # Capability gating — check at handler entry
    for cap in REQUIRED_CAPABILITIES:
        if not enabled(cap):
            return unavailable(cap)

    # Clamp limit
    limit = max(1, min(limit, 25))

    # Default to all kinds
    if kinds is None:
        kinds = ["contact", "company", "deal"]
    else:
        # Validate kinds
        valid_kinds = {"contact", "company", "deal"}
        kinds = [k for k in kinds if k in valid_kinds]
        if not kinds:
            kinds = ["contact", "company", "deal"]

    repo: CrmRepository = get_repository()
    result: SearchResult = repo.search_crm(query, kinds=kinds, limit=limit)

    # Build the note
    note = None
    if result.total == 0:
        note = (
            "Nothing in the CRM matches. That is an answer: say so rather "
            "than asking the rep to search for you. Try a shorter or "
            "differently spelled term first — a surname alone often works "
            "where a full name does not."
        )
    elif result.total > 1:
        note = (
            "More than one match. If it is genuinely ambiguous, name the "
            "candidates and ask which — never ask for an id."
        )

    return {
        "query": result.query,
        "contacts": [
            {
                "kind": "contact",
                "id": c.id,
                "name": c.name,
                "title": c.title,
                "email": c.email,
                "company": c.company,
                "lastActivityAt": c.lastActivityAt,
            }
            for c in result.contacts
        ],
        "companies": [
            {
                "kind": "company",
                "id": c.id,
                "name": c.name,
                "domain": c.domain,
                "industry": c.industry,
                "contacts": c.contacts,
                "deals": c.deals,
            }
            for c in result.companies
        ],
        "deals": [
            {
                "kind": "deal",
                "id": d.id,
                "name": d.name,
                "stage": d.stage,
                "amount": d.amount,
                "currency": d.currency,
                "company": d.company,
            }
            for d in result.deals
        ],
        "total": result.total,
        "note": note,
    }
