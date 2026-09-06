"""
CRM company lookup skill handler.

Port of CRM company lookup — resolves a company by id or finds companies
by domain. Uses the CRM repository interface so it works with both the
mock and a real backend.

The repository is injectable (``set_repository`` / module-level ``_REPO``)
so tests can seed a mock without touching the global module import.
"""

from __future__ import annotations

from typing import Optional

from system.crm_repository import CrmRepository, MockCrmRepository
from system.capabilities import enabled, unavailable

# Capability check — this skill uses the CRM repository.
REQUIRED_CAPABILITIES: list[str] = []

# Injectable repository. Defaults to a fresh MockCrmRepository; tests (and
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
    company_id: Optional[str] = None,
    domain: Optional[str] = None,
) -> dict:
    """
    Look up a company by id or find companies by domain.

    Args:
        company_id: A company id to look up exactly.
        domain: A domain to search for companies (e.g. "acme.com").

    Returns:
        If company_id provided: {"ok": True, "company": <dict>} or
        {"ok": False, "error": "Company not found"}.
        If domain provided: {"ok": True, "companies": <list[dict]>}.
        If neither provided: {"ok": False, "error": "Provide company_id or domain"}.
        If capability not enabled: {"ok": False, "error": <unavailable dict>}.
    """
    # Capability gating — check at handler entry
    for cap in REQUIRED_CAPABILITIES:
        if not enabled(cap):
            return unavailable(cap)

    # Validate input: exactly one of company_id or domain must be provided
    if company_id is None and domain is None:
        return {"ok": False, "error": "Provide company_id or domain"}
    if company_id is not None and domain is not None:
        return {"ok": False, "error": "Provide either company_id or domain, not both"}

    repo: CrmRepository = get_repository()

    if company_id is not None:
        company = repo.company_by_id(company_id)
        if company is None:
            return {"ok": False, "error": "Company not found"}
        return {"ok": True, "company": company}

    # domain is not None
    companies = repo.companies_by_domain(domain)
    return {"ok": True, "companies": companies}