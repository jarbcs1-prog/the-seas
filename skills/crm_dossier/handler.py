"""
CRM dossier skill handler.

Port of CRM `fullDossier` tool — assembles a complete contact dossier
including email threads, meetings, deals, companies, and social handles.
Uses the CRM repository interface so it works with both the mock and a
real backend.

The repository is injectable (``set_repository`` / module-level ``_REPO``)
so tests can seed a mock without touching the global module import.
"""

from __future__ import annotations

from typing import Optional

from system.crm_repository import CrmRepository, MockCrmRepository
from system.capabilities import enabled, unavailable

# Capability check — this skill uses the CRM repository. Gate on "crm".
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
    contact_id: Optional[str] = None,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> dict:
    """
    Assemble a full contact dossier.

    Args:
        contact_id: The CRM contact ID. If provided, used directly.
        name: Full name of the contact (used with exact_contacts lookup).
        email: Email address of the contact (used with exact_contacts lookup).

    Returns:
        A dict with:
        - ok: True if successful, False if capability missing or not found
        - dossier: The full dossier dict (when ok=True) containing:
            - name: Contact's full name
            - email: Contact's email
            - handles: List of social handles
            - threads: List of email threads
            - meetings: List of meetings
            - deals: List of deals
            - companies: List of companies
            - notes: Plain-language notes for missing data
        - error: Error dict (when ok=False)
    """
    # Capability gating — check at handler entry
    for cap in REQUIRED_CAPABILITIES:
        if not enabled(cap):
            return unavailable(cap)

    repo: CrmRepository = get_repository()

    # Resolve contact_id if not provided
    resolved_id = contact_id
    if resolved_id is None:
        if name is not None or email is not None:
            matches = repo.exact_contacts(name=name, email=email)
            if len(matches) == 1:
                resolved_id = matches[0].get("id")
            elif len(matches) > 1:
                return {
                    "ok": False,
                    "error": {
                        "ok": False,
                        "configured": True,
                        "reason": (
                            f"Multiple contacts match name={name!r} email={email!r}. "
                            "Provide a contact_id to disambiguate."
                        ),
                    },
                }
            else:
                return {
                    "ok": False,
                    "error": {
                        "ok": False,
                        "configured": True,
                        "reason": (
                            f"No contact found for name={name!r} email={email!r}."
                        ),
                    },
                }
        else:
            return {
                "ok": False,
                "error": {
                    "ok": False,
                    "configured": True,
                    "reason": "Must provide contact_id, name, or email.",
                },
            }

    # Fetch the full dossier
    dossier = repo.full_dossier(resolved_id)
    if not dossier:
        return {
            "ok": False,
            "error": {
                "ok": False,
                "configured": True,
                "reason": f"No contact found with id={resolved_id!r}.",
            },
        }

    return {"ok": True, "dossier": dossier}