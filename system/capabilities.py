"""
Capability System — port of CRM lib/capabilities.ts.

Checks environment variables at startup and provides gating functions
that skills call at handler entry to determine whether a given source
is available.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Capability record — mirrors CRM Capability type
# ---------------------------------------------------------------------------


@dataclass
class Capability:
    """A capability gated by an environment variable."""

    env: str = ""           # environment variable name
    label: str = ""         # human-readable label
    gives: str = ""         # what this capability provides
    enabled: bool = False   # whether the env var is set


# ---------------------------------------------------------------------------
# Known capabilities — mirrors CRM capabilities() return value
# ---------------------------------------------------------------------------


def _env_set(key: str) -> bool:
    """Check whether an environment variable is set and non-empty."""
    value = os.environ.get(key, "")
    return bool(value and value.strip())


_CAPABILITIES: list[Capability] = [
    Capability(
        env="RAPIDAPI_KEY",
        label="LinkedIn",
        gives=(
            "a person's real name, current title, employer and tenure, "
            "self-reported and so authoritative on identity"
        ),
        enabled=_env_set("RAPIDAPI_KEY"),
    ),
    Capability(
        env="PERPLEXITY_API_KEY",
        label="Web research",
        gives=(
            "open-web context with citations and the search that finds "
            "a LinkedIn slug in the first place"
        ),
        enabled=_env_set("PERPLEXITY_API_KEY"),
    ),
    Capability(
        env="CONTEXT_DEV_API_KEY",
        label="Company brand data",
        gives=(
            "a company's logo, industry, location and socials from its domain"
        ),
        enabled=_env_set("CONTEXT_DEV_API_KEY"),
    ),
    Capability(
        env="BLOB_READ_WRITE_TOKEN",
        label="Picture storage",
        gives=(
            "somewhere to keep a logo or a profile photo. Without it a "
            "record has no picture at all, because the URLs these sources "
            "hand back expire and are never stored as they are"
        ),
        enabled=_env_set("BLOB_READ_WRITE_TOKEN"),
    ),
    # Added for The S.E.A.S. integration — CRM also uses AGENT_BRIDGE_SECRET
    # for session isolation in the sandbox.
    Capability(
        env="AGENT_BRIDGE_SECRET",
        label="Session isolation",
        gives=(
            "signed tokens for sandbox session isolation — without it "
            "the sandbox cannot distinguish one session from another"
        ),
        enabled=_env_set("AGENT_BRIDGE_SECRET"),
    ),
]


def all_capabilities() -> list[Capability]:
    """Return the full list of known capabilities with their status.

    Recomputes ``enabled`` live from the environment so callers see the
    current configuration rather than a snapshot taken at import time.
    """
    return [
        Capability(
            env=c.env,
            label=c.label,
            gives=c.gives,
            enabled=_env_set(c.env),
        )
        for c in _CAPABILITIES
    ]


def enabled(env: str) -> bool:
    """Check whether a capability (by env var name) is available.

    Port of CRM lib/capabilities.ts enabled().  Reads the environment
    live so it reflects configuration set after import.
    """
    return _env_set(env)


def unavailable(env: str) -> dict:
    """Return an unavailability result for a capability.

    Port of CRM lib/capabilities.ts unavailable().
    """
    return {
        "ok": False,
        "configured": False,
        "reason": (
            f"This install has no {env}, so that source is unavailable. "
            "This is not a failure and retrying will not help — "
            "use what the CRM already knows and say in your write-up "
            "what you could not check."
        ),
    }


def capabilities_markdown() -> str:
    """Generate a markdown summary of available and unavailable capabilities.

    Port of CRM lib/capabilities.ts capabilitiesMarkdown().
    """
    all_caps = all_capabilities()
    on = [c for c in all_caps if c.enabled]
    off = [c for c in all_caps if not c.enabled]

    lines: list[str] = ["## What you can use here", ""]

    if len(on) == 0:
        lines.extend([
            "No outside sources are configured on this install. Everything you can",
            "learn is already in the CRM — email threads, meetings, signature",
            "blocks — and `read_crm_history` reads all of it for free. That is",
            "often enough to settle who somebody is. Record what it shows, and",
            "leave the rest empty.",
        ])
        return "\n".join(lines)

    lines.append("Available:")
    for cap in on:
        lines.append(f"- **{cap.label}** — {cap.gives}.")

    if len(off) > 0:
        lines.append("")
        lines.append(
            "Not configured here, so do not plan around them:"
        )
        for cap in off:
            lines.append(f"- {cap.label}")
        lines.extend([
            "",
            "Their tools will tell you the same thing if you call them. Note what",
            "you could not check rather than guessing at it.",
        ])

    return "\n".join(lines)


def startup_status() -> dict:
    """Return a startup status summary for logging.

    Called once at system startup to print what's configured.
    """
    all_caps = all_capabilities()
    configured = [c for c in all_caps if c.enabled]
    missing = [c for c in all_caps if not c.enabled]

    return {
        "configured": [c.label for c in configured],
        "missing": [c.label for c in missing],
        "total": len(all_caps),
        "ready": len(configured) > 0,
    }
