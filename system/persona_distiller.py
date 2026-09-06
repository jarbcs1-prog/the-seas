"""Persona Distiller — distills L3 Core/Persona constraints from validated capabilities.

Ports TCM's L3 Persona Distillation concept (``core/persona-generation.ts``) into
SEAS's self-improvement pipeline.  Runs after capability promotion to extract
stable, reusable behavioral constraints that guide future agent behaviour.

The distiller scans ``capabilities_memory.json`` for capabilities at level >= 3
with validation_score > 0.7, extracts constraint patterns from each
``lesson`` + ``scope`` pair, deduplicates similar constraints via fuzzy string
matching, and writes the result to ``persona_constraints.json``.

Persona constraints are stored alongside the existing SEAS self-improvement
data so they can be injected into the agent's runtime context via
``reflection_bridge.py``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .reflection_model import ReflectionStore, PromotionLevel

# Default paths (SEAS ai-self-reflection skill directory)
BASE_DIR = Path(__file__).resolve().parent.parent
AI_REFLECTION_DIR = BASE_DIR / "skills" / "ai-self-reflection"
DEFAULT_CAPABILITIES_PATH = AI_REFLECTION_DIR / "capabilities_memory.json"
DEFAULT_PERSONA_PATH = BASE_DIR / "system" / "persona_constraints.json"

# Distillation thresholds (from extraction plan)
MIN_LEVEL = 3
MIN_VALIDATION_SCORE = 0.7
MIN_CAPABILITIES_FOR_DISTILL = 2
MAX_CONSTRAINT_TOKENS = 500  # Cap at ~500 tokens per persona constraint
FUZZY_MATCH_THRESHOLD = 0.8  # 80% similarity to consider constraints duplicates


@dataclass
class PersonaConstraint:
    """A distilled behavioral constraint derived from validated capabilities.

    Fields:
        id: Stable unique identifier for this constraint.
        trigger: The scope keyword that activates this constraint.
        constraint: The distilled behavioral constraint text.
        source_capabilities: List of capability lesson strings this was distilled from.
        confidence: Confidence score (0.0 to 1.0) — max of source capabilities.
        applied_count: How many times this constraint has been applied at runtime.
        created: ISO timestamp of first distillation.
        last_applied: ISO timestamp of last runtime application (empty if never).
    """

    id: str
    trigger: str
    constraint: str
    source_capabilities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    applied_count: int = 0
    created: str = ""
    last_applied: str = ""

    def __post_init__(self):
        if not self.id:
            seed = f"{self.trigger}:{self.constraint}:{self.created}"
            self.id = f"persona-{hashlib.md5(seed.encode()).hexdigest()[:8]}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PersonaConstraint":
        return cls(**data)


def _load_json(path: Path) -> list[dict]:
    """Load JSON data from file, returning empty list on error."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_json(path: Path, data: list[dict]) -> None:
    """Save JSON data to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _capability_id(cap: dict) -> str:
    """Generate a stable ID for a capability entry.

    Mirrors the pattern used in comprehensive_cli.py: hash of lesson + created.
    """
    seed = f"{cap.get('lesson', '')}:{cap.get('created', '')}"
    digest = hashlib.md5(seed.encode()).hexdigest()[:8]
    return f"instinct-{digest}"


def _extract_constraint(cap: dict) -> str:
    """Extract a distilled constraint string from a capability entry.

    Combines the lesson (the principle) with the action (how to apply it),
    producing a concise, reusable behavioral constraint.
    """
    lesson = cap.get("lesson", "").strip()
    action = cap.get("action", "").strip()
    scope = cap.get("scope", "").strip()

    if action:
        constraint = f"{lesson} — {action}"
    else:
        constraint = lesson

    if scope:
        constraint = f"{constraint} [scope: {scope}]"

    # Truncate to token budget (~500 tokens ≈ 2000 chars)
    if len(constraint) > MAX_CONSTRAINT_TOKENS * 4:
        constraint = constraint[: MAX_CONSTRAINT_TOKENS * 4 - 3] + "..."

    return constraint


def _extract_trigger(cap: dict) -> str:
    """Extract the trigger (scope) that activates this constraint."""
    return cap.get("scope", "").strip() or "general"


def _similarity(a: str, b: str) -> float:
    """Compute text similarity ratio between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, a, b).ratio()


def _deduplicate_constraints(
    raw_constraints: list[tuple[dict, str, str]],
) -> list[dict]:
    """Deduplicate constraint entries using fuzzy string matching.

    Args:
        raw_constraints: List of (capability, trigger, constraint) tuples.

    Returns:
        List of consolidated capability dicts, where similar constraints
        have been merged into a single entry with combined source capabilities.
    """
    merged: list[dict] = []

    for cap, trigger, constraint in raw_constraints:
        # Look for an existing merged entry with similar trigger + constraint
        matched_idx = None
        best_similarity = 0.0

        for i, existing in enumerate(merged):
            if existing["trigger"] == trigger:
                sim = _similarity(constraint, existing["constraint"])
                if sim > FUZZY_MATCH_THRESHOLD and sim > best_similarity:
                    best_similarity = sim
                    matched_idx = i

        if matched_idx is not None:
            # Merge into existing
            existing = merged[matched_idx]
            existing["source_capabilities"].append(_capability_id(cap))
            existing["confidence"] = max(
                existing["confidence"], cap.get("confidence", 0.0)
            )
        else:
            # Create new merged entry
            merged.append(
                {
                    "trigger": trigger,
                    "constraint": constraint,
                    "source_capabilities": [_capability_id(cap)],
                    "confidence": cap.get("confidence", 0.0),
                }
            )

    return merged


def _distill_from_capability(cap: dict) -> tuple[str, str]:
    """Distill a single capability into (trigger, constraint) pair."""
    trigger = _extract_trigger(cap)
    constraint = _extract_constraint(cap)
    return trigger, constraint


def distill_persona(
    capabilities_path: Path | str = DEFAULT_CAPABILITIES_PATH,
    output_path: Path | str = DEFAULT_PERSONA_PATH,
    min_level: int = MIN_LEVEL,
    min_validation_score: float = MIN_VALIDATION_SCORE,
) -> list[PersonaConstraint]:
    """Distill persona constraints from validated level-3 capabilities.

    Scans ``capabilities_memory.json`` for capabilities at or above
    ``min_level`` with validation_score > ``min_validation_score``,
    extracts reusable constraint patterns, deduplicates similar constraints
    via fuzzy string matching, and writes the result to ``persona_constraints.json``.

    Args:
        capabilities_path: Path to the capabilities_memory.json file.
        output_path: Path to write persona_constraints.json.
        min_level: Minimum promotion level to consider (default: 3 = General Capability).
        min_validation_score: Minimum validation score (default: 0.7).

    Returns:
        List of distilled PersonaConstraint objects.
    """
    capabilities = _load_json(Path(capabilities_path))

    # Filter: level >= min_level and validation_score > min_validation_score
    # Also require at least MIN_CAPABILITIES_FOR_DISTILL qualifying capabilities
    # (per risk mitigation: min 2 capability groups with matching scope)
    qualifying = [
        cap
        for cap in capabilities
        if cap.get("level", 0) >= min_level
        and cap.get("validation_score", 0.0) > min_validation_score
    ]

    if len(qualifying) < MIN_CAPABILITIES_FOR_DISTILL:
        # Not enough qualifying capabilities for distillation
        return []

    # Extract constraints from each qualifying capability
    raw_constraints: list[tuple[dict, str, str]] = []
    for cap in qualifying:
        trigger, constraint = _distill_from_capability(cap)
        if constraint:
            raw_constraints.append((cap, trigger, constraint))

    # Deduplicate via fuzzy matching
    merged = _deduplicate_constraints(raw_constraints)

    # Build PersonaConstraint objects
    now = datetime.now().isoformat()
    constraints: list[PersonaConstraint] = []

    for entry in merged:
        constraint = PersonaConstraint(
            id="",
            trigger=entry["trigger"],
            constraint=entry["constraint"],
            source_capabilities=entry["source_capabilities"],
            confidence=round(entry["confidence"], 4),
            applied_count=0,
            created=now,
            last_applied="",
        )
        constraints.append(constraint)

    # Save to disk
    _save_json(Path(output_path), [c.to_dict() for c in constraints])

    return constraints


def load_constraints(
    path: Path | str = DEFAULT_PERSONA_PATH,
) -> list[PersonaConstraint]:
    """Load persona constraints from disk."""
    data = _load_json(Path(path))
    return [PersonaConstraint.from_dict(d) for d in data]


def get_active_constraints(
    scope: str = "general",
    path: Path | str = DEFAULT_PERSONA_PATH,
) -> list[PersonaConstraint]:
    """Retrieve persona constraints matching a given scope.

    A constraint is included if:
    - Its trigger matches the scope (case-insensitive substring match), or
    - Its trigger is 'general' (applies everywhere)
    """
    constraints = load_constraints(path)
    scope_lower = scope.lower().strip()

    active = []
    for c in constraints:
        trigger_lower = c.trigger.lower().strip()
        if trigger_lower == "general" or scope_lower in trigger_lower or trigger_lower in scope_lower:
            active.append(c)

    # Sort by confidence (descending), then applied_count (ascending for less-used first)
    active.sort(key=lambda x: (-x.confidence, x.applied_count))
    return active


def apply_constraint(constraint_id: str, path: Path | str = DEFAULT_PERSONA_PATH) -> bool:
    """Mark a persona constraint as applied (increments applied_count)."""
    constraints = load_constraints(path)
    updated = False

    for c in constraints:
        if c.id == constraint_id:
            c.applied_count += 1
            c.last_applied = datetime.now().isoformat()
            updated = True
            break

    if updated:
        _save_json(Path(path), [c.to_dict() for c in constraints])

    return updated


def build_constraints_block(
    scope: str = "general",
    path: Path | str = DEFAULT_PERSONA_PATH,
    max_tokens: int = 500,
) -> str:
    """Build a persona constraints prompt overlay for injection into system context.

    Args:
        scope: The current scope to filter constraints by.
        path: Path to persona_constraints.json.
        max_tokens: Maximum token budget for the constraints block.

    Returns:
        A formatted constraints block string, or empty string if no constraints.
    """
    active = get_active_constraints(scope, path)

    if not active:
        return ""

    header = "\n### PERSONA CONSTRAINTS (Distilled from Level-3 Capabilities)\n"
    lines: list[str] = [header]
    current_chars = len(header)
    max_chars = int(max_tokens * 4)  # Rough char-to-token ratio

    for c in active:
        line = f"- {c.constraint} (confidence: {c.confidence:.2f}, applied: {c.applied_count}x)"
        if current_chars + len(line) + 1 > max_chars:
            break
        lines.append(line)
        current_chars += len(line) + 1

    return "\n".join(lines)
