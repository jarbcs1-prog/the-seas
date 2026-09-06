"""
CRM Repository Interface — abstract data access layer.

Models the Prisma query shapes from the CRM TypeScript source
(lib/lookup.ts, lib/crm.ts, lib/brand.ts, lib/facts.ts) behind a
Python interface.  A mock implementation is provided for tests;
the real implementation is wired when a CRM data source is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Search result types (from lib/lookup.ts)
# ---------------------------------------------------------------------------


@dataclass
class ContactHit:
    """A contact search result."""

    kind: str = "contact"
    id: str = ""
    name: str = ""
    title: Optional[str] = None
    email: Optional[str] = None
    company: Optional[dict] = None  # {id, name}
    lastActivityAt: Optional[str] = None


@dataclass
class CompanyHit:
    """A company search result."""

    kind: str = "company"
    id: str = ""
    name: str = ""
    domain: Optional[str] = None
    industry: Optional[str] = None
    contacts: int = 0
    deals: int = 0


@dataclass
class DealHit:
    """A deal search result."""

    kind: str = "deal"
    id: str = ""
    name: str = ""
    stage: str = ""
    amount: Optional[float] = None
    currency: str = ""
    company: dict = field(default_factory=dict)  # {id, name}


# A search hit is one of the three above — we use a union via typing.
SearchHit = ContactHit | CompanyHit | DealHit


@dataclass
class SearchResult:
    """Aggregate search result from lookup.ts/searchCrm."""

    query: str = ""
    contacts: list[ContactHit] = field(default_factory=list)
    companies: list[CompanyHit] = field(default_factory=list)
    deals: list[DealHit] = field(default_factory=list)
    total: int = 0
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# CRM history types (from lib/crm.ts — CrmHistory)
# ---------------------------------------------------------------------------


@dataclass
class CrmContact:
    """Contact summary within a full dossier."""

    fullName: str = ""
    email: Optional[str] = None
    title: Optional[str] = None
    companyName: Optional[str] = None
    company: Optional[dict] = None  # {id, name, domain, industry}


@dataclass
class CrmDeal:
    """A deal associated with a contact."""

    id: str = ""
    name: str = ""
    stage: str = ""
    role: Optional[str] = None
    amount: Optional[float] = None
    currency: str = ""
    expectedCloseDate: Optional[str] = None


@dataclass
class CrmMessage:
    """A single message within an email thread."""

    direction: str = ""  # "INBOUND" | "OUTBOUND"
    from_email: str = ""
    fromName: Optional[str] = None
    sentAt: str = ""
    body: Optional[str] = None


@dataclass
class CrmThread:
    """An email thread."""

    subject: Optional[str] = None
    messageCount: int = 0
    lastMessageAt: str = ""
    messages: list[CrmMessage] = field(default_factory=list)


@dataclass
class CrmMeeting:
    """A calendar event."""

    title: Optional[str] = None
    startsAt: str = ""
    attended: bool = False
    attendees: list[dict] = field(default_factory=list)  # {email, name}


@dataclass
class CrmStats:
    """Aggregate stats for a contact dossier."""

    emails: int = 0
    theyReplied: bool = False
    lastReplyAt: Optional[str] = None
    meetings: int = 0
    nextMeetingAt: Optional[str] = None


@dataclass
class CrmColleague:
    """A colleague (other contact at same company)."""

    id: str = ""
    name: str = ""
    title: Optional[str] = None


@dataclass
class CrmHistory:
    """Full CRM dossier for a contact (from lib/crm.ts readCrmHistory)."""

    contact: CrmContact = field(default_factory=CrmContact)
    deals: list[CrmDeal] = field(default_factory=list)
    threads: list[CrmThread] = field(default_factory=list)
    meetings: list[CrmMeeting] = field(default_factory=list)
    stats: CrmStats = field(default_factory=CrmStats)
    colleagues: list[CrmColleague] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Company enrichment types (from lib/brand.ts)
# ---------------------------------------------------------------------------

COMPANY_FIELDS = {
    "id": True,
    "name": True,
    "domain": True,
    "description": True,
    "logoUrl": True,
    "logoDarkUrl": True,
    "iconUrl": True,
    "iconDarkUrl": True,
    "iconTone": True,
    "brandColor": True,
    "industry": True,
    "subIndustry": True,
    "city": True,
    "stateCode": True,
    "country": True,
    "countryCode": True,
    "phone": True,
    "email": True,
    "linkedinUrl": True,
    "twitterUrl": True,
    "githubUrl": True,
    "pricingUrl": True,
    "careersUrl": True,
}


@dataclass
class BrandResult:
    """Result of a company brand enrichment run."""

    enriched: bool = False
    filled: list[str] = field(default_factory=list)
    mirrored: list[str] = field(default_factory=list)
    reason: Optional[str] = None
    retryable: bool = False


# ---------------------------------------------------------------------------
# Fact types (from lib/facts.ts)
# ---------------------------------------------------------------------------

FACT_FIELDS = [
    "name",
    "title",
    "linkedinUrl",
    "twitterUrl",
    "githubUrl",
    "employer",
    "seniority",
    "function",
    "location",
    "tenure",
]


from system.evidence_ledger import Evidence
@dataclass
class RecordFactInput:
    """Input to recordFact (from lib/facts.ts)."""

    contactId: str = ""
    fact_field: str = ""  # one of FACT_FIELDS
    value: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    method: str = ""
    sourceUrl: Optional[str] = None


@dataclass
class RecordFactResult:
    """Result of recordFact."""

    stored: bool = False
    applied: bool = False
    band: Optional[str] = None  # FactBand: VERIFIED | PROBABLE | POSSIBLE
    score: float = 0.0
    rationale: str = ""
    reason: Optional[str] = None


@dataclass
class EmployerChange:
    """Detected employer change (from lib/facts.ts lastEmployerChange)."""

    from_value: str = ""
    to: str = ""
    observedAt: str = ""
    sourceUrl: Optional[str] = None


@dataclass
class BriefSections:
    """Brief sections for writeBrief."""

    currentRole: Optional[str] = None
    tenure: Optional[str] = None
    previousRoles: list[str] = field(default_factory=list)
    seniority: Optional[str] = None
    function: Optional[str] = None
    location: Optional[str] = None


# ---------------------------------------------------------------------------
# Work item types (from lib/crm.ts — contactsNeedingWork)
# ---------------------------------------------------------------------------


@dataclass
class WorkItem:
    """A contact that needs work (identity, brief, socials)."""

    id: str = ""
    fullName: str = ""
    email: Optional[str] = None
    title: Optional[str] = None
    companyName: Optional[str] = None
    companyDomain: Optional[str] = None
    linkedinUrl: Optional[str] = None
    needs_identity: bool = False
    needs_brief: bool = False
    needs_socials: bool = False


# ---------------------------------------------------------------------------
# Repository interface
# ---------------------------------------------------------------------------


@runtime_checkable
class CrmRepository(Protocol):
    """Abstract interface for CRM data access.

    Implement this with a real backend (e.g. Prisma/SQL queries via an
    adapter) or a mock for testing.  The shape mirrors the Prisma query
    signatures from the CRM TypeScript source.
    """

    # -- Search (lib/lookup.ts) --

    def search_contacts(
        self, term: str, words: list[str], email: Optional[str], limit: int
    ) -> list[ContactHit]:
        """Search contacts by name, email, or company name."""
        ...

    def search_companies(
        self, term: str, words: list[str], domain: Optional[str], limit: int
    ) -> list[CompanyHit]:
        """Search companies by name or domain."""
        ...

    def search_deals(self, term: str, words: list[str], limit: int) -> list[DealHit]:
        """Search deals by name or company name."""
        ...

    def search_crm(
        self, query: str, kinds: Optional[list[str]] = None, limit: int = 10
    ) -> SearchResult:
        """Full-text CRM search across contacts, companies, and deals."""
        ...

    # -- CRM history (lib/crm.ts) --

    def read_crm_history(
        self,
        contact_id: str,
        threads: Optional[int] = None,
        messages_per_thread: Optional[int] = None,
    ) -> Optional[CrmHistory]:
        """Read the full dossier for a contact."""
        ...

    def contacts_needing_work(self, limit: int) -> list[WorkItem]:
        """Find contacts needing identity, brief, or socials work."""
        ...

    def person_for_verification(self, contact_id: str) -> Optional[dict]:
        """Get a person's details for social verification."""
        ...

    def contact_profile_slug(self, contact_id: str) -> Optional[dict]:
        """Extract LinkedIn slug from a contact's linkedinUrl."""
        ...

    def stamp_socials_checked(self, contact_id: str) -> None:
        """Mark socials as checked on a contact."""
        ...

    def write_timeline_note(
        self, contact_id: str, subject: str, body: str, meta: Optional[dict] = None
    ) -> Optional[str]:
        """Write a timeline note (activity) for a contact."""
        ...

    # -- Company enrichment (lib/brand.ts) --

    def get_company(self, company_id: str) -> Optional[dict]:
        """Get a company by ID with all COMPANY_FIELDS."""
        ...

    def run_brand(
        self, company_id: str, fresh: bool = False, spend_units: int = 2
    ) -> BrandResult:
        """Run brand enrichment for a company."""
        ...

    # -- Facts (lib/facts.ts) --

    def record_fact(self, input: RecordFactInput) -> RecordFactResult:
        """Record a fact about a contact with evidence scoring."""
        ...

    def last_employer_change(self, contact_id: str) -> Optional[EmployerChange]:
        """Detect a previous to current employer change."""
        ...

    def write_brief(
        self,
        contact_id: str,
        narrative: str,
        sections: BriefSections,
        evidence: list[Evidence],
        source_url: Optional[str] = None,
    ) -> dict:
        """Write a brief for a contact."""
        ...

    def get_contact(self, contact_id: str) -> Optional[dict]:
        """Get a contact by ID (for fact checks)."""
        ...

    def get_existing_facts(self, contact_id: str, field: str) -> list[dict]:
        """Get existing facts for a contact field."""
        ...

    # -- Roadmap-specified lookup surface (lib/lookup.ts) --

    def contact_by_id(self, contact_id: str) -> Optional[dict]:
        """Get a single contact by id (lib/lookup.ts contactById)."""
        ...

    def contacts_by_email(self, email: str) -> list[dict]:
        """Contacts whose email matches exactly (contactsByEmail)."""
        ...

    def contacts_by_domain(self, domain: str) -> list[dict]:
        """Contacts at a domain (contactsByDomain)."""
        ...

    def exact_contacts(
        self, name: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        """Exact-match contact lookup by full name or email (exactContacts)."""
        ...

    def companies_by_domain(self, domain: str) -> list[dict]:
        """Companies at a domain (domainCompanies)."""
        ...

    def company_by_id(self, company_id: str) -> Optional[dict]:
        """Get a single company by id."""
        ...

    def enrich_company(
        self, domain: str, logo_path: Optional[str] = None
    ) -> BrandResult:
        """Enrich a company from context.dev brand records (lib/brand.ts)."""
        ...

    def deals_for_contact(self, contact_id: str) -> list[dict]:
        """Deals associated with a contact (dealsForContact)."""
        ...

    def companies_for_contact(self, contact_id: str) -> list[dict]:
        """Companies a contact belongs to (companiesForContact)."""
        ...

    def threads_for_contact(self, contact_id: str) -> list[dict]:
        """Email threads for a contact (threadsForContact)."""
        ...

    def meetings_for_contact(self, contact_id: str) -> list[dict]:
        """Meetings for a contact (meetingsForContact)."""
        ...

    def handles_for_contact(self, contact_id: str) -> list[dict]:
        """Social handles for a contact (handlesForContact)."""
        ...

    def contacts_for_company(self, company_id: str) -> list[dict]:
        """Contacts at a company (contactsForCompany)."""
        ...

    def full_dossier(self, contact_id: str) -> dict:
        """Assemble a contact dossier with CRM 'no data' notes.

        Ports lib/crm.ts readContactDossier shape: name, email, handles,
        threads, meetings, deals, companies, plus plain-language notes
        when any of those are missing (so the agent never invents them).
        """
        ...


# ---------------------------------------------------------------------------
# Mock repository — for testing without a live CRM
# ---------------------------------------------------------------------------


class MockCrmRepository:
    """In-memory mock CRM repository.

    Pre-populated with minimal fixture data so tests can run without
    a live database.  Extend the fixtures as test cases require more.
    """

    def __init__(self):
        self._contacts: dict[str, dict] = {}
        self._companies: dict[str, dict] = {}
        self._deals: dict[str, dict] = {}
        self._facts: dict[str, list[dict]] = {}
        self._briefs: dict[str, dict] = {}
        self._threads: dict[str, list[dict]] = {}
        self._meetings: list[dict] = []
        self._activities: list[dict] = []
        # Roadmap-specified lookup surface
        self._handles: dict[str, list[dict]] = {}      # contact_id -> [handle]
        self._notes: dict[str, list[dict]] = {}        # contact_id -> [note]
        self._brand_records: dict[str, list[dict]] = {}  # domain -> [record]

    # -- Helpers --

    @staticmethod
    def _full_name(c: dict) -> str:
        parts = [c.get("firstName", ""), c.get("lastName", "")]
        return " ".join(p for p in parts if p)

    @staticmethod
    def _slug_from_url(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        import re

        m = re.search(r"linkedin\.com/in/([A-Za-z0-9\-_%]+)", url)
        return m.group(1) if m else None

    @staticmethod
    def _domain_from_email(email: Optional[str]) -> Optional[str]:
        if not email or "@" not in email:
            return None
        return email.split("@")[1].lower()

    @staticmethod
    def _bare_domain(term: str) -> Optional[str]:
        """Return ``term`` if it looks like a bare domain, else None.

        Ports CRM lib/lookup.ts ``bareDomain`` so a raw domain query
        (e.g. ``fernhill.com``) is matched against company domains.
        """
        import re

        candidate = term.strip().lower().replace("https://", "").replace(
            "http://", ""
        )
        return (
            candidate
            if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", candidate)
            else None
        )

    # -- Search --

    def search_contacts(
        self, term: str, words: list[str], email: Optional[str], limit: int
    ) -> list[ContactHit]:
        term_lc = term.lower()
        results: list[ContactHit] = []
        for cid, c in self._contacts.items():
            name = self._full_name(c)
            if (
                term_lc in name.lower()
                or term_lc in (c.get("email") or "").lower()
                or term_lc in (c.get("title") or "").lower()
                or term_lc in ((c.get("company") or {}).get("name", "") or "").lower()
                or any(w.lower() in name.lower() for w in words)
            ):
                results.append(
                    ContactHit(
                        kind="contact",
                        id=cid,
                        name=name,
                        title=c.get("title"),
                        email=c.get("email"),
                        company=c.get("company"),
                        lastActivityAt=c.get("lastActivityAt"),
                    )
                )
        # Also match by email
        if email:
            for cid, c in self._contacts.items():
                if c.get("email", "").lower() == email.lower():
                    if not any(r.id == cid for r in results):
                        results.append(
                            ContactHit(
                                kind="contact",
                                id=cid,
                                name=self._full_name(c),
                                title=c.get("title"),
                                email=c.get("email"),
                                company=c.get("company"),
                                lastActivityAt=c.get("lastActivityAt"),
                            )
                        )
        results.sort(key=lambda r: r.name)
        return results[:limit]

    def search_companies(
        self, term: str, words: list[str], domain: Optional[str], limit: int
    ) -> list[CompanyHit]:
        term_lc = term.lower()
        results: list[CompanyHit] = []
        for cid, c in self._companies.items():
            name = c.get("name", "")
            cdomain = c.get("domain") or ""
            if (
                term_lc in name.lower()
                or (domain and domain.lower() in cdomain.lower())
                or any(w.lower() in name.lower() for w in words)
            ):
                results.append(
                    CompanyHit(
                        kind="company",
                        id=cid,
                        name=name,
                        domain=cdomain or None,
                        industry=c.get("industry"),
                        contacts=c.get("contacts", 0),
                        deals=c.get("deals", 0),
                    )
                )
        results.sort(key=lambda r: r.name)
        return results[:limit]

    def search_deals(
        self, term: str, words: list[str], limit: int
    ) -> list[DealHit]:
        term_lc = term.lower()
        results: list[DealHit] = []
        for did, d in self._deals.items():
            name = d.get("name", "")
            company_name = d.get("company", {}).get("name", "")
            if (
                term_lc in name.lower()
                or term_lc in company_name.lower()
                or any(w.lower() in name.lower() for w in words)
            ):
                results.append(
                    DealHit(
                        kind="deal",
                        id=did,
                        name=name,
                        stage=d.get("stage", ""),
                        amount=d.get("amount"),
                        currency=d.get("currency", ""),
                        company=d.get("company", {}),
                    )
                )
        results.sort(key=lambda r: r.name)
        return results[:limit]

    def search_crm(
        self,
        query: str,
        kinds: Optional[list[str]] = None,
        limit: int = 10,
    ) -> SearchResult:
        kinds = kinds or ["contact", "company", "deal"]
        words = [w for w in query.split() if len(w) >= 2]
        email = query.lower() if "@" in query else None
        domain = self._domain_from_email(email) if email else self._bare_domain(query)
        contacts = (
            self.search_contacts(query, words, email, limit)
            if "contact" in kinds
            else []
        )
        companies = (
            self.search_companies(query, words, domain, limit)
            if "company" in kinds
            else []
        )
        deals = (
            self.search_deals(query, words, limit) if "deal" in kinds else []
        )
        note = None
        if len(contacts) + len(companies) + len(deals) == 0:
            note = (
                "Nothing in the CRM matches. That is an answer: say so rather "
                "than asking the rep to search for you. Try a shorter or "
                "differently spelled term first — a surname alone often works "
                "where a full name does not."
            )
        elif len(contacts) + len(companies) + len(deals) > 1:
            note = (
                "More than one match. If it is genuinely ambiguous, name the "
                "candidates and ask which — never ask for an id."
            )
        return SearchResult(
            query=query.strip(),
            contacts=contacts,
            companies=companies,
            deals=deals,
            total=len(contacts) + len(companies) + len(deals),
            note=note,
        )

    # -- CRM history --

    def read_crm_history(
        self,
        contact_id: str,
        threads: Optional[int] = None,
        messages_per_thread: Optional[int] = None,
    ) -> Optional[CrmHistory]:
        c = self._contacts.get(contact_id)
        if not c:
            return None
        threads_list = self._threads.get(contact_id, [])
        stats = CrmStats(
            emails=sum(t.get("messageCount", 0) for t in threads_list),
            theyReplied=any(
                m.get("direction") == "INBOUND"
                for t in threads_list
                for m in t.get("messages", [])
            ),
            lastReplyAt=max(
                [
                    m.get("sentAt")
                    for t in threads_list
                    for m in t.get("messages", [])
                    if m.get("direction") == "INBOUND"
                ],
                default=None,
            ),
            meetings=len(self._meetings),
            nextMeetingAt=None,
        )
        return CrmHistory(
            contact=CrmContact(
                fullName=self._full_name(c),
                email=c.get("email"),
                title=c.get("title"),
                companyName=(c.get("company") or {}).get("name"),
                company=c.get("company"),
            ),
            deals=[
                CrmDeal(
                    id=d.get("id", ""),
                    name=d.get("name", ""),
                    stage=d.get("stage", ""),
                    role=d.get("role"),
                    amount=d.get("amount"),
                    currency=d.get("currency", ""),
                    expectedCloseDate=d.get("expectedCloseDate"),
                )
                for d in c.get("deals", [])
            ],
            threads=[
                CrmThread(
                    subject=t.get("subject"),
                    messageCount=t.get("messageCount", 0),
                    lastMessageAt=t.get("lastMessageAt", ""),
                    messages=[
                        CrmMessage(
                            direction=m.get("direction", ""),
                            from_email=m.get("from_email", ""),
                            fromName=m.get("fromName"),
                            sentAt=m.get("sentAt", ""),
                            body=m.get("body"),
                        )
                        for m in t.get("messages", [])[: messages_per_thread or 6]
                    ],
                )
                for t in threads_list[: threads or 5]
            ],
            meetings=[
                CrmMeeting(
                    title=m.get("title"),
                    startsAt=m.get("startsAt", ""),
                    attended=m.get("attended", False),
                    attendees=m.get("attendees", []),
                )
                for m in self._meetings
            ],
            stats=stats,
            colleagues=[
                CrmColleague(
                    id=col.get("id", ""),
                    name=self._full_name(col),
                    title=col.get("title"),
                )
                for col in c.get("colleagues", [])
            ],
        )

    def contacts_needing_work(self, limit: int) -> list[WorkItem]:
        results: list[WorkItem] = []
        for cid, c in sorted(
            self._contacts.items(), key=lambda kv: kv[1].get("createdAt", "")
        ):
            if len(results) >= limit:
                break
            email = c.get("email")
            first = c.get("firstName", "")
            last = c.get("lastName")
            needs_identity = (
                email
                and not last
                and self._slug_from_url(c.get("linkedinUrl")) is None
            )
            needs_brief = c.get("brief") is None
            needs_socials = c.get("socialsCheckedAt") is None
            if needs_identity or needs_brief or needs_socials:
                results.append(
                    WorkItem(
                        id=cid,
                        fullName=self._full_name(c),
                        email=email,
                        title=c.get("title"),
                        companyName=(c.get("company") or {}).get("name"),
                        companyDomain=(
                            (c.get("company") or {}).get("domain")
                            or self._domain_from_email(email)
                        ),
                        linkedinUrl=c.get("linkedinUrl"),
                        needs_identity=needs_identity,
                        needs_brief=needs_brief,
                        needs_socials=needs_socials,
                    )
                )
        return results

    def person_for_verification(self, contact_id: str) -> Optional[dict]:
        c = self._contacts.get(contact_id)
        if not c:
            return None
        return {
            "firstName": c.get("firstName", ""),
            "lastName": c.get("lastName"),
            "fullName": self._full_name(c),
            "title": c.get("title"),
            "companyName": (c.get("company") or {}).get("name"),
            "companyDomain": (
                (c.get("company") or {}).get("domain")
                or self._domain_from_email(c.get("email"))
            ),
        }

    def contact_profile_slug(self, contact_id: str) -> Optional[dict]:
        c = self._contacts.get(contact_id)
        if not c:
            return None
        slug = self._slug_from_url(c.get("linkedinUrl"))
        if not slug:
            return None
        return {"slug": slug, "profileUrl": f"https://www.linkedin.com/in/{slug}"}

    def stamp_socials_checked(self, contact_id: str) -> None:
        if contact_id in self._contacts:
            self._contacts[contact_id]["socialsCheckedAt"] = datetime.now().isoformat()

    def write_timeline_note(
        self,
        contact_id: str,
        subject: str,
        body: str,
        meta: Optional[dict] = None,
    ) -> Optional[str]:
        if contact_id not in self._contacts:
            return None
        activity = {
            "id": f"act-{len(self._activities) + 1:04d}",
            "type": "NOTE",
            "subject": subject,
            "body": body,
            "occurredAt": datetime.now().isoformat(),
            "contactId": contact_id,
            "companyId": self._contacts[contact_id].get("companyId"),
            "createdById": self._contacts[contact_id].get("ownerId"),
            "meta": {**(meta or {}), "agent": "people-research"},
        }
        self._activities.append(activity)
        return activity["id"]

    # -- Company enrichment --

    def get_company(self, company_id: str) -> Optional[dict]:
        return self._companies.get(company_id)

    def run_brand(
        self,
        company_id: str,
        fresh: bool = False,
        spend_units: int = 2,
    ) -> BrandResult:
        company = self._companies.get(company_id)
        if not company:
            return BrandResult(enriched=False, reason="No such company.")
        domain = company.get("domain")
        if not domain:
            return BrandResult(enriched=False, reason="No domain on this company.")
        filled: list[str] = []
        mirrored: list[str] = []
        # Simulate enrichment: fill missing fields from domain
        for field in ["description", "industry", "city", "country"]:
            if not company.get(field) and domain:
                company[field] = f"Enriched from {domain} ({field})"
                filled.append(field)
        if "logoUrl" not in filled and not company.get("logoUrl"):
            company["logoUrl"] = f"https://{domain}/logo.png"
            filled.append("logoUrl")
            mirrored.append("logoUrl")
        return BrandResult(
            enriched=True,
            filled=filled,
            mirrored=mirrored,
        )

    # -- Facts --

    def record_fact(self, input: RecordFactInput) -> RecordFactResult:
        from system.evidence_ledger import score_evidence

        evidence = input.evidence or []
        scored = score_evidence(evidence)
        if not input.value.strip():
            return RecordFactResult(
                stored=False,
                applied=False,
                band=scored.band,
                score=scored.score,
                rationale=scored.rationale,
                reason="Empty value.",
            )
        if scored.band is None:
            return RecordFactResult(
                stored=False,
                applied=False,
                band=None,
                score=0.0,
                rationale=scored.rationale,
                reason=(
                    "Below the floor for keeping — not stored. Find a source "
                    "that identifies them or leave the field alone."
                ),
            )
        if input.contactId not in self._contacts:
            return RecordFactResult(
                stored=False,
                applied=False,
                band=scored.band,
                score=scored.score,
                rationale=scored.rationale,
                reason="No such contact.",
            )
        # Check for dismissed fact with same value
        existing = self._facts.get(input.contactId, [])
        for fact in existing:
            if (
                fact.get("status") == "DISMISSED"
                and fact.get("value", "").strip().lower()
                == input.value.strip().lower()
            ):
                return RecordFactResult(
                    stored=False,
                    applied=False,
                    band=scored.band,
                    score=scored.score,
                    rationale=scored.rationale,
                    reason=(
                        "A person has already dismissed this exact value. "
                        "Do not offer it again."
                    ),
                )
        # Check for already-applied fact with same value
        # (CRM allows multiple facts per field with different statuses;
        #  only return early if the exact same value is already APPLIED —
        #  in that case nothing has changed.)
        applied_same_value = next(
            (f for f in existing if f.get("status") == "APPLIED"
             and f.get("value", "").strip().lower() == input.value.strip().lower()),
            None,
        )
        if applied_same_value:
            return RecordFactResult(
                stored=False,
                applied=False,
                band=scored.band,
                score=scored.score,
                rationale=scored.rationale,
                reason="Already on the record, from this same source. Nothing changed.",
            )
        # Determine if applies (VERIFIED → applies)
        applies = scored.band == "VERIFIED"
        # Find the prior APPLIED fact for this field (if any) — we will
        # supersede it when the new fact is also APPLIED.
        prior_applied = next(
            (f for f in existing if f.get("field") == input.fact_field
             and f.get("status") == "APPLIED"),
            None,
        )
        new_fact_entry = {
            "contactId": input.contactId,
            "field": input.fact_field,
            "value": input.value.strip(),
            "score": scored.score,
            "band": scored.band,
            "evidence": [e.__dict__ for e in evidence],
            "method": input.method,
            "sourceUrl": input.sourceUrl,
            "status": "APPLIED" if applies else "PROPOSED",
        }
        existing.append(new_fact_entry)
        self._facts.setdefault(input.contactId, []).append(new_fact_entry)
        if applies and prior_applied:
            # Supersede the old APPLIED fact for this field
            for f in self._facts[input.contactId]:
                if f.get("field") == input.fact_field and f.get("status") == "APPLIED":
                    f["status"] = "SUPERSEDED"
                    f["supersededAt"] = datetime.now().isoformat()
        result_reason = None
        if not applies:
            result_reason = (
                "Kept as a proposal for a rep to accept or dismiss. This is a "
                "normal outcome, not a failure — do not try to raise the score."
            )
        return RecordFactResult(
            stored=True,
            applied=applies,
            band=scored.band,
            score=scored.score,
            rationale=scored.rationale,
            reason=result_reason,
        )

    def last_employer_change(self, contact_id: str) -> Optional[EmployerChange]:
        facts = self._facts.get(contact_id, [])
        previous = next(
            (
                f
                for f in facts
                if f.get("field") == "employer" and f.get("status") == "SUPERSEDED"
            ),
            None,
        )
        current = next(
            (
                f
                for f in facts
                if f.get("field") == "employer" and f.get("status") == "APPLIED"
            ),
            None,
        )
        if not previous or not current:
            return None
        if previous.get("value", "").strip().lower() == current.get("value", "").strip().lower():
            return None
        return EmployerChange(
            from_value=previous.get("value", ""),
            to=current.get("value", ""),
            observedAt=current.get("observedAt", ""),
            sourceUrl=current.get("sourceUrl"),
        )

    def write_brief(
        self,
        contact_id: str,
        narrative: str,
        sections: BriefSections,
        evidence: list[Evidence],
        source_url: Optional[str] = None,
    ) -> dict:
        from system.evidence_ledger import score_evidence

        scored = score_evidence(evidence)
        if scored.band is None:
            return {
                "written": False,
                "score": scored.score,
                "reason": "Nothing here is sourced well enough to put on the record.",
            }
        self._briefs[contact_id] = {
            "contactId": contact_id,
            "narrative": narrative.strip(),
            "sections": {
                "currentRole": sections.currentRole,
                "tenure": sections.tenure,
                "previousRoles": sections.previousRoles,
                "seniority": sections.seniority,
                "function": sections.function,
                "location": sections.location,
            },
            "score": scored.score,
            "sourceUrl": source_url,
            "refreshedAt": datetime.now().isoformat(),
        }
        return {"written": True, "score": scored.score}

    def get_contact(self, contact_id: str) -> Optional[dict]:
        return self._contacts.get(contact_id)

    def get_existing_facts(self, contact_id: str, field: str) -> list[dict]:
        return [
            f
            for f in self._facts.get(contact_id, [])
            if f.get("field") == field
        ]

    # -- Roadmap-specified lookup surface --

    def contact_by_id(self, contact_id: str) -> Optional[dict]:
        return self._contacts.get(contact_id)

    def contacts_by_email(self, email: str) -> list[dict]:
        if not email:
            return []
        target = email.lower()
        out: list[dict] = []
        seen = set()
        for cid, c in self._contacts.items():
            if (c.get("email") or "").lower() == target:
                out.append(c)
                seen.add(cid)
        # Also include contacts at the email's domain (contactsByEmail matches
        # domain contacts too, per the roadmap test signals).
        domain = self._domain_from_email(target)
        if domain:
            for cid, c in self._contacts.items():
                if cid in seen:
                    continue
                comp = c.get("company") or {}
                comp_domain = comp.get("domain") if isinstance(comp, dict) else None
                if comp_domain and comp_domain.lower() == domain:
                    out.append(c)
                    seen.add(cid)
        return out

    def contacts_by_domain(self, domain: str) -> list[dict]:
        if not domain:
            return []
        target = domain.lower()
        return [
            c
            for c in self._contacts.values()
            if (c.get("company") or {}).get("domain", "").lower() == target
        ]

    def exact_contacts(
        self, name: Optional[str] = None, email: Optional[str] = None
    ) -> list[dict]:
        out: list[dict] = []
        seen = set()
        if email:
            target = email.lower()
            for cid, c in self._contacts.items():
                if (c.get("email") or "").lower() == target:
                    out.append(c)
                    seen.add(cid)
        if name:
            target = name.strip().lower()
            for cid, c in self._contacts.items():
                if cid in seen:
                    continue
                if self._full_name(c).lower() == target:
                    out.append(c)
                    seen.add(cid)
        return out

    def companies_by_domain(self, domain: str) -> list[dict]:
        if not domain:
            return []
        target = domain.lower()
        return [
            c
            for c in self._companies.values()
            if (c.get("domain") or "").lower() == target
        ]

    def company_by_id(self, company_id: str) -> Optional[dict]:
        return self._companies.get(company_id)

    def deals_for_contact(self, contact_id: str) -> list[dict]:
        c = self._contacts.get(contact_id)
        return list(c.get("deals", [])) if c else []

    def companies_for_contact(self, contact_id: str) -> list[dict]:
        c = self._contacts.get(contact_id)
        if not c:
            return []
        comp = c.get("company")
        if not isinstance(comp, dict):
            return []
        cid = comp.get("id")
        return [self._companies[cid]] if cid and cid in self._companies else []

    def threads_for_contact(self, contact_id: str) -> list[dict]:
        return list(self._threads.get(contact_id, []))

    def meetings_for_contact(self, contact_id: str) -> list[dict]:
        c = self._contacts.get(contact_id)
        email = (c or {}).get("email")
        if not email:
            return []
        out = []
        for m in self._meetings:
            for att in m.get("attendees", []):
                if att.get("email") == email:
                    out.append(m)
                    break
        return out

    def handles_for_contact(self, contact_id: str) -> list[dict]:
        return list(self._handles.get(contact_id, []))

    def contacts_for_company(self, company_id: str) -> list[dict]:
        return [
            c
            for c in self._contacts.values()
            if (c.get("company") or {}).get("id") == company_id
        ]

    def enrich_company(
        self, domain: str, logo_path: Optional[str] = None
    ) -> BrandResult:
        company = None
        for c in self._companies.values():
            if (c.get("domain") or "").lower() == (domain or "").lower():
                company = c
                break
        if company is None:
            return BrandResult(
                enriched=False,
                reason=(
                    f"The CRM has no company named {domain} on file. "
                    "Don't guess or invent a company."
                ),
            )
        records = self._brand_records.get((domain or "").lower(), [])
        if not records:
            return BrandResult(
                enriched=False,
                reason=(
                    f"context.dev returned no records for {domain}. "
                    "Don't guess or invent a company."
                ),
            )
        chosen = self._select_brand_record(records, logo_path)
        filled: list[str] = []
        mirrored: list[str] = []
        for field in ("industry", "location", "website", "logoUrl"):
            if not company.get(field) and chosen.get(field):
                company[field] = chosen[field]
                filled.append(field)
                if field == "logoUrl":
                    mirrored.append(field)
        return BrandResult(
            enriched=len(filled) > 0,
            filled=filled,
            mirrored=mirrored,
            reason=f"Matched {len(records)} record(s) for {domain}.",
        )

    @staticmethod
    def _select_brand_record(records: list[dict], logo_path: Optional[str]) -> dict:
        if logo_path:
            target_base = logo_path.rsplit("/", 1)[-1].lower()
            best = None
            best_score = -1
            for r in records:
                rp = (r.get("logoPath") or "").lower()
                base = rp.rsplit("/", 1)[-1]
                if base == target_base:
                    return r
                score = sum(1 for a, b in zip(base, target_base) if a == b)
                if score > best_score:
                    best_score = score
                    best = r
            if best is not None:
                return best
        # Too few records for meaningful similarity → first record.
        if len(records) <= 2:
            return records[0]
        # Otherwise pick the record with the most specific logo path.
        return max(records, key=lambda r: len(r.get("logoPath") or ""))

    def full_dossier(self, contact_id: str) -> dict:
        c = self._contacts.get(contact_id)
        if not c:
            return {}
        name = self._full_name(c)
        email = c.get("email")
        handles = self.handles_for_contact(contact_id)
        threads = self.threads_for_contact(contact_id)
        meetings = self.meetings_for_contact(contact_id)
        deals = self.deals_for_contact(contact_id)
        companies = self.companies_for_contact(contact_id)
        notes: list[str] = []
        if not handles:
            notes.append(f"No social handles are on file for {name} in the CRM.")
        if not threads:
            notes.append(f"The CRM has no email threads on file for {name}.")
        if not deals:
            notes.append(f"The CRM has no deals on file for {name}.")
        if not companies:
            notes.append(f"{name} doesn't belong to any company in the CRM.")
        else:
            comp = companies[0]
            missing = [f for f in ("industry", "location", "website") if not comp.get(f)]
            if missing:
                if len(missing) == 1:
                    phrase = missing[0]
                else:
                    phrase = ", ".join(missing[:-1]) + ", or " + missing[-1]
                notes.append(
                    f"{name} belongs to a company in the CRM with no known "
                    f"{phrase}; say so plainly and do not make one up."
                )
        # Internal notes are intentionally NOT included in the dossier.
        return {
            "name": name,
            "email": email,
            "handles": handles,
            "threads": threads,
            "meetings": meetings,
            "deals": deals,
            "companies": companies,
            "notes": notes,
        }

    # -- Fixtures --

    def add_contact(
        self,
        contact_id: str,
        first_name: str = "",
        last_name: str = "",
        email: Optional[str] = None,
        title: Optional[str] = None,
        company_id: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        deals: Optional[list[dict]] = None,
    ) -> dict:
        company = None
        if company_id and company_id in self._companies:
            company = {
                "id": company_id,
                "name": self._companies[company_id].get("name", ""),
                "domain": self._companies[company_id].get("domain"),
                "industry": self._companies[company_id].get("industry"),
            }
        contact = {
            "id": contact_id,
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "title": title,
            "linkedinUrl": linkedin_url,
            "company": company,
            "companyId": company_id,
            "ownerId": None,
            "createdAt": datetime.now().isoformat(),
            "brief": None,
            "socialsCheckedAt": None,
            "lastActivityAt": datetime.now().isoformat(),
            "deals": deals or [],
        }
        # Register any deals attached to the contact so they are searchable
        # via search_deals / search_crm (mirrors the CRM where a deal is a
        # first-class, queryable record, not just a contact sub-list).
        for d in deals or []:
            did = d.get("id")
            if did and did not in self._deals:
                self._deals[did] = d
                if company_id and company_id in self._companies:
                    self._companies[company_id]["deals"] = (
                        self._companies[company_id].get("deals", 0) + 1
                    )
        self._contacts[contact_id] = contact
        return contact

    def add_company(
        self,
        company_id: str,
        name: str = "",
        domain: Optional[str] = None,
        industry: Optional[str] = None,
    ) -> dict:
        company = {
            "id": company_id,
            "name": name,
            "domain": domain,
            "industry": industry,
            "contacts": 0,
            "deals": 0,
        }
        self._companies[company_id] = company
        return company

    def add_deal(
        self,
        deal_id: str,
        name: str = "",
        stage: str = "",
        amount: Optional[float] = None,
        currency: str = "",
        company_id: Optional[str] = None,
    ) -> dict:
        company = None
        if company_id and company_id in self._companies:
            company = {
                "id": company_id,
                "name": self._companies[company_id].get("name", ""),
            }
        deal = {
            "id": deal_id,
            "name": name,
            "stage": stage,
            "amount": amount,
            "currency": currency,
            "company": company or {},
        }
        self._deals[deal_id] = deal
        if company_id and company_id in self._companies:
            self._companies[company_id]["deals"] = self._companies[company_id].get("deals", 0) + 1
        return deal

    def add_thread(
        self,
        contact_id: str,
        subject: Optional[str] = None,
        messages: Optional[list[dict]] = None,
    ) -> dict:
        thread = {
            "subject": subject,
            "messageCount": len(messages or []),
            "lastMessageAt": (
                max((m.get("sentAt") for m in (messages or [])), default="")
            ),
            "messages": messages or [],
        }
        self._threads.setdefault(contact_id, []).append(thread)
        return thread

    def add_meeting(
        self,
        title: Optional[str] = None,
        starts_at: str = "",
        attended: bool = False,
        attendees: Optional[list[dict]] = None,
    ) -> dict:
        meeting = {
            "title": title,
            "startsAt": starts_at,
            "attended": attended,
            "attendees": attendees or [],
        }
        self._meetings.append(meeting)
        return meeting

    def add_handle(
        self,
        contact_id: str,
        platform: str,
        url: str,
        internal: bool = False,
    ) -> dict:
        handle = {"platform": platform, "url": url, "internal": internal}
        self._handles.setdefault(contact_id, []).append(handle)
        return handle

    def add_note(
        self,
        contact_id: str,
        body: str,
        internal: bool = True,
    ) -> dict:
        note = {"body": body, "internal": internal}
        self._notes.setdefault(contact_id, []).append(note)
        return note

    def add_brand_record(
        self,
        domain: str,
        logo_path: str,
        industry: Optional[str] = None,
        location: Optional[str] = None,
        website: Optional[str] = None,
        logo_url: Optional[str] = None,
    ) -> dict:
        record = {
            "logoPath": logo_path,
            "industry": industry,
            "location": location,
            "website": website,
            "logoUrl": logo_url,
        }
        self._brand_records.setdefault(domain.lower(), []).append(record)
        return record
