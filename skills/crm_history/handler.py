"""
CRM history skill handler.

Port of CRM `readCrmHistory` tool — reads the full dossier for a contact
including deals, email threads, meetings, stats, and colleagues.
Uses the CRM repository interface so it works with both the mock and a real backend.

The repository is injectable (``set_repository`` / module-level ``_REPO``)
so tests can seed a mock without touching the global module import.
"""

from __future__ import annotations

from typing import Optional

from system.crm_repository import CrmRepository, MockCrmRepository, CrmHistory
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


def _crm_history_to_dict(history: CrmHistory) -> dict:
    """Convert a CrmHistory dataclass to a plain dict for JSON serialization."""
    return {
        "contact": {
            "fullName": history.contact.fullName,
            "email": history.contact.email,
            "title": history.contact.title,
            "companyName": history.contact.companyName,
            "company": history.contact.company,
        },
        "deals": [
            {
                "id": d.id,
                "name": d.name,
                "stage": d.stage,
                "role": d.role,
                "amount": d.amount,
                "currency": d.currency,
                "expectedCloseDate": d.expectedCloseDate,
            }
            for d in history.deals
        ],
        "threads": [
            {
                "subject": t.subject,
                "messageCount": t.messageCount,
                "lastMessageAt": t.lastMessageAt,
                "messages": [
                    {
                        "direction": m.direction,
                        "from": m.from_email,
                        "fromName": m.fromName,
                        "sentAt": m.sentAt,
                        "body": m.body,
                    }
                    for m in t.messages
                ],
            }
            for t in history.threads
        ],
        "meetings": [
            {
                "title": m.title,
                "startsAt": m.startsAt,
                "attended": m.attended,
                "attendees": m.attendees,
            }
            for m in history.meetings
        ],
        "stats": {
            "emails": history.stats.emails,
            "theyReplied": history.stats.theyReplied,
            "lastReplyAt": history.stats.lastReplyAt,
            "meetings": history.stats.meetings,
            "nextMeetingAt": history.stats.nextMeetingAt,
        },
        "colleagues": [
            {
                "id": c.id,
                "name": c.name,
                "title": c.title,
            }
            for c in history.colleagues
        ],
    }


def execute(
    contact_id: str,
    threads: Optional[int] = None,
    messages_per_thread: Optional[int] = None,
) -> dict:
    """
    Read the full CRM dossier for a contact.

    Args:
        contact_id: The CRM contact ID to look up.
        threads: Maximum number of email threads to return (default 5).
        messages_per_thread: Maximum messages per thread (default 6).

    Returns:
        A dict with:
        - ok: True if successful, False if capability gated or not found
        - history: list containing the dossier dict (empty list if not found)
        - error: error message if ok is False
    """
    # Capability gating — check at handler entry
    for cap in REQUIRED_CAPABILITIES:
        if not enabled(cap):
            return unavailable(cap)

    repo: CrmRepository = get_repository()
    history: Optional[CrmHistory] = repo.read_crm_history(
        contact_id,
        threads=threads,
        messages_per_thread=messages_per_thread,
    )

    if history is None:
        return {"ok": False, "error": f"Contact not found: {contact_id}", "history": []}

    return {"ok": True, "history": [_crm_history_to_dict(history)]}