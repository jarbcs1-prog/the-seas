#!/usr/bin/env python3
"""Comprehensive CLI for ai-self-reflection skill - persistent learning system."""

import argparse
import getpass
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REFLECTION_EVENTS = BASE / "reflection_events.json"
CAPABILITIES_MEMORY = BASE / "capabilities_memory.json"
VALIDATION_HISTORY = BASE / "validation_history.json"
FRICTION_LOG = BASE / "friction_log.md"
PERSONA_CONSTRAINTS = BASE.parent / "system" / "persona_constraints.json"

# Import the persona distiller from SEAS system module
try:
    from system.persona_distiller import (
        distill_persona,
        load_constraints,
        get_active_constraints,
        build_constraints_block,
        PersonaConstraint,
    )
except ImportError:
    # Allow CLI to function even if system module is not on path
    distill_persona = None
    load_constraints = None
    get_active_constraints = None
    build_constraints_block = None
    PersonaConstraint = None


# ==================== Memory Helpers ====================


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return []


def save_json(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, indent=2))


# ==================== Commands ====================


def cmd_initialize(args: argparse.Namespace) -> int:
    """Initialize memory structure."""
    for path, init in [
        (REFLECTION_EVENTS, []),
        (CAPABILITIES_MEMORY, []),
        (VALIDATION_HISTORY, []),
    ]:
        if not path.exists() or args.force:
            save_json(path, init)
            print(f"Initialized {path.name}")
        else:
            print(f"{path.name} already exists (use --force to reset)")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Record a reflection event to experience memory."""
    events = load_json(REFLECTION_EVENTS)

    event = {
        "timestamp": datetime.now().isoformat(),
        "task": args.task,
        "category": args.category,
        "observation": args.observation,
        "friction": args.friction,
        "root_cause": args.root_cause,
        "lesson": args.lesson,
        "scope": args.scope,
        "confidence": args.confidence,
        "evidence": args.evidence,
        "action": args.action,
        "level": 0,  # Observation level
    }

    events.append(event)
    save_json(REFLECTION_EVENTS, events)
    print(f"Recorded reflection event (total: {len(events)})")
    return 0


def cmd_distill(args: argparse.Namespace) -> int:
    """Distill experiences into candidate lessons (level 1)."""
    events = load_json(REFLECTION_EVENTS)
    capabilities = load_json(CAPABILITIES_MEMORY)

    # Group by (lesson, scope) to find repeated patterns
    groups = defaultdict(list)
    for e in events:
        if e.get("level", 0) == 0:  # Only observations
            key = (e["lesson"], e["scope"])
            groups[key].append(e)

    promoted = 0
    for (lesson, scope), group in groups.items():
        if len(group) >= args.min_evidence:
            # Calculate average confidence
            avg_confidence = sum(e["confidence"] for e in group) / len(group)
            evidence_count = len(group)
            categories = [e["category"] for e in group]
            category_counts = Counter(categories)
            primary_category = category_counts.most_common(1)[0][0]

            # Check if already exists as capability
            existing = None
            for cap in capabilities:
                if cap["lesson"] == lesson and cap["scope"] == scope:
                    existing = cap
                    break

            if existing:
                # Update existing candidate
                existing["evidence"] = evidence_count
                existing["confidence"] = min(1.0, avg_confidence + 0.05)
                existing["last_updated"] = datetime.now().isoformat()
                existing["supporting_events"] = [e["timestamp"] for e in group]
            else:
                # Create new candidate lesson (level 1)
                capabilities.append(
                    {
                        "lesson": lesson,
                        "scope": scope,
                        "category": primary_category,
                        "confidence": avg_confidence,
                        "evidence": evidence_count,
                        "level": 1,  # Candidate Lesson
                        "created": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat(),
                        "supporting_events": [e["timestamp"] for e in group],
                        "validation_score": 0.0,
                        "promotion_history": [
                            {"level": 1, "date": datetime.now().isoformat()}
                        ],
                    }
                )
                promoted += 1

    save_json(CAPABILITIES_MEMORY, capabilities)
    print(f"Distilled {promoted} new candidate lessons (level 1)")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote validated candidates to higher capability levels."""
    capabilities = load_json(CAPABILITIES_MEMORY)

    promoted = 0
    for cap in capabilities:
        current_level = cap.get("level", 1)
        confidence = cap.get("confidence", 0)
        evidence = cap.get("evidence", 0)
        validation_score = cap.get("validation_score", 0)

        # Promotion criteria
        if current_level == 1:  # Candidate → Local Adaptation
            if evidence >= 3 and confidence >= 0.7 and validation_score >= 0.5:
                cap["level"] = 2
                cap["promotion_history"].append(
                    {"level": 2, "date": datetime.now().isoformat()}
                )
                promoted += 1
        elif current_level == 2:  # Local → General Capability
            if evidence >= 5 and confidence >= 0.8 and validation_score >= 0.7:
                cap["level"] = 3
                cap["promotion_history"].append(
                    {"level": 3, "date": datetime.now().isoformat()}
                )
                promoted += 1

    save_json(CAPABILITIES_MEMORY, capabilities)
    print(f"Promoted {promoted} capabilities")

    # Auto-run persona distillation if any capabilities reached level 3
    if promoted > 0 and distill_persona is not None:
        try:
            constraints = distill_persona(
                capabilities_path=CAPABILITIES_MEMORY,
                output_path=PERSONA_CONSTRAINTS,
            )
            if constraints:
                print(f"Distilled {len(constraints)} persona constraints")
        except Exception as e:
            print(f"[warn] persona distillation skipped: {e}")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Record capability validation outcome."""
    capabilities = load_json(CAPABILITIES_MEMORY)
    validations = load_json(VALIDATION_HISTORY)

    # Find capability by name/lesson
    cap = None
    for c in capabilities:
        if c["lesson"] == args.capability:
            cap = c
            break

    if not cap:
        print(f"Capability '{args.capability}' not found")
        return 1

    success = args.success
    delta = args.delta

    # Update validation score (exponential moving average)
    old_score = cap.get("validation_score", 0.0)
    alpha = 0.3
    new_score = old_score + alpha * ((1.0 if success else 0.0) - old_score)
    cap["validation_score"] = round(new_score, 3)
    cap["last_validated"] = datetime.now().isoformat()

    # Adjust confidence based on outcome
    if success:
        cap["confidence"] = min(1.0, cap["confidence"] + delta)
    else:
        cap["confidence"] = max(0.0, cap["confidence"] - delta)

    # Record validation
    validations.append(
        {
            "timestamp": datetime.now().isoformat(),
            "capability": args.capability,
            "task": args.task,
            "outcome": args.outcome,
            "success": success,
            "delta": delta,
            "previous_score": old_score,
            "new_score": cap["validation_score"],
        }
    )

    save_json(CAPABILITIES_MEMORY, capabilities)
    save_json(VALIDATION_HISTORY, validations)

    status = "[OK]" if success else "[FAIL]"
    print(
        f"{status} Validated '{args.capability}' - score: {cap['validation_score']:.3f}, confidence: {cap['confidence']:.3f}"
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate system report."""
    events = load_json(REFLECTION_EVENTS)
    capabilities = load_json(CAPABILITIES_MEMORY)
    validations = load_json(VALIDATION_HISTORY)

    # Level distribution
    level_counts = Counter(c.get("level", 0) for c in capabilities)
    level_names = {
        0: "Observation",
        1: "Candidate Lesson",
        2: "Local Adaptation",
        3: "General Capability",
    }

    # Category distribution
    cat_counts = Counter(c.get("category", "unknown") for c in capabilities)

    # Recent validations
    recent_validations = sorted(
        validations, key=lambda x: x["timestamp"], reverse=True
    )[:10]

    # Top capabilities by validation_score * confidence
    ranked = sorted(
        [c for c in capabilities if c.get("level", 0) >= 2],
        key=lambda x: x.get("validation_score", 0) * x.get("confidence", 0),
        reverse=True,
    )[:5]

    # Persona constraints coverage
    persona_section = {"total": 0, "coverage": 0.0, "by_trigger": {}}
    if load_constraints is not None:
        try:
            persona_constraints = load_constraints(PERSONA_CONSTRAINTS)
            # Count qualifying level-3 capabilities (level >= 3, validation_score > 0.7)
            qualifying = [
                c for c in capabilities
                if c.get("level", 0) >= 3 and c.get("validation_score", 0) > 0.7
            ]
            # Coverage: what fraction of qualifying caps contributed to persona constraints
            source_ids = set()
            for pc in persona_constraints:
                source_ids.update(pc.source_capabilities)
            coverage = 0.0
            if qualifying:
                coverage = len(source_ids) / len(qualifying)
            trigger_counts = Counter()
            for pc in persona_constraints:
                trigger_counts[pc.trigger] += 1
            persona_section = {
                "total": len(persona_constraints),
                "coverage": round(coverage, 2),
                "qualifying_caps": len(qualifying),
                "by_trigger": dict(trigger_counts),
            }
        except Exception as e:
            persona_section = {"total": 0, "coverage": 0.0, "error": str(e)}

    report = {
        "experience_events": len(events),
        "capabilities": {
            "total": len(capabilities),
            "by_level": {level_names[k]: v for k, v in level_counts.items()},
            "by_category": dict(cat_counts),
        },
        "validations": {
            "total": len(validations),
            "recent": recent_validations,
        },
        "top_capabilities": [
            {
                "lesson": c["lesson"],
                "scope": c["scope"],
                "level": level_names.get(c.get("level", 0), "Unknown"),
                "confidence": c.get("confidence", 0),
                "validation_score": c.get("validation_score", 0),
                "composite": c.get("validation_score", 0) * c.get("confidence", 0),
            }
            for c in ranked
        ],
        "persona": persona_section,
    }

    print(json.dumps(report, indent=2))
    return 0


def cmd_bridge(args: argparse.Namespace) -> int:
    """Generate capability bridge constraints for runtime injection."""
    capabilities = load_json(CAPABILITIES_MEMORY)
    scope = args.scope

    # Filter capabilities matching scope (general or specific)
    matching = [
        c
        for c in capabilities
        if c.get("level", 0) >= 2
        and (
            scope == "general"
            or scope.lower() in c.get("scope", "").lower()
            or c.get("scope", "").lower() in scope.lower()
        )
    ]

    # Rank by composite score
    ranked = sorted(
        matching,
        key=lambda x: x.get("validation_score", 0) * x.get("confidence", 0),
        reverse=True,
    )

    # Build constraints within token budget
    constraints = []
    tokens = 0
    budget = args.budget

    for cap in ranked:
        constraint = f"- {cap['lesson']} (scope: {cap['scope']}, confidence: {cap['confidence']:.2f})"
        constraint_tokens = len(constraint.split()) * 1.3  # rough estimate
        if tokens + constraint_tokens > budget:
            break
        constraints.append(constraint)
        tokens += constraint_tokens

    result = {
        "scope": scope,
        "token_budget": budget,
        "estimated_tokens": int(tokens),
        "constraints": constraints,
        "active_capabilities": len(constraints),
    }

    print(json.dumps(result, indent=2))
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    """Prune old memory records."""
    limit = args.limit

    for path in [REFLECTION_EVENTS, VALIDATION_HISTORY]:
        data = load_json(path)
        if len(data) > limit:
            original = len(data)
            # Keep most recent
            data = sorted(data, key=lambda x: x.get("timestamp", ""), reverse=True)[
                :limit
            ]
            save_json(path, data)
            print(f"Pruned {path.name}: {original} → {len(data)}")
        else:
            print(f"{path.name}: {len(data)} records (under limit)")

    return 0


# ==================== Instincts Export ====================


def _count_successful_validations(
    capability_lesson: str, validations: list[dict]
) -> int:
    """Count successful validations for a given capability lesson."""
    return sum(
        1
        for v in validations
        if v.get("capability") == capability_lesson and v.get("success")
    )


def _capability_id(cap: dict) -> str:
    """Generate a stable instinct ID from a capability entry."""
    seed = f"{cap.get('lesson', '')}:{cap.get('created', '')}"
    digest = hashlib.md5(seed.encode()).hexdigest()[:8]
    return f"instinct-{digest}"


def _build_instinct(cap: dict, validations: list[dict]) -> dict:
    """Convert a capability memory entry into an instinct export record."""
    lesson = cap.get("lesson", "")
    return {
        "id": _capability_id(cap),
        "trigger": cap.get("scope", ""),
        "action": lesson,
        "confidence": round(cap.get("confidence", 0.0), 4),
        "category": cap.get("category", "unknown"),
        "applications": cap.get("evidence", 0),
        "successes": _count_successful_validations(lesson, validations),
        "source": "session-observation",
    }


def _build_filter_description(args: argparse.Namespace) -> str:
    """Build a human-readable filter description for metadata."""
    parts = []
    if args.min_confidence is not None:
        parts.append(f"confidence >= {args.min_confidence}")
    if args.category:
        parts.append(f"category == {args.category}")
    if not parts:
        return "all"
    return ", ".join(parts)


def _print_export_report(instincts: list[dict], metadata: dict) -> None:
    """Print the export report to stdout."""
    filtered = len(instincts)
    total = metadata["total"]

    cat_counts = Counter(i["category"] for i in instincts)

    ranked = sorted(instincts, key=lambda x: x["confidence"], reverse=True)[:5]

    print("\nExport Summary")
    print("==============")
    print(f"Output: {metadata.get('file', 'stdout')}")
    print(f"Total instincts: {total}")
    print(f"Filtered: {filtered}")
    print(f"Exported: {filtered}")
    print()
    print("Categories:")
    for cat, count in cat_counts.most_common():
        print(f"- {cat}: {count}")
    print()
    print("Top Instincts (by confidence):")
    for i, instinct in enumerate(ranked, 1):
        print(f"{i}. {instinct['trigger']} ({instinct['confidence']:.2f})")


def cmd_instincts_export(args: argparse.Namespace) -> int:
    """Export validated capabilities as instincts JSON."""
    capabilities = load_json(CAPABILITIES_MEMORY)
    validations = load_json(VALIDATION_HISTORY)

    instincts = [_build_instinct(c, validations) for c in capabilities]

    # Apply filters
    if args.min_confidence is not None:
        instincts = [i for i in instincts if i["confidence"] >= args.min_confidence]
    if args.category:
        instincts = [i for i in instincts if i["category"] == args.category]

    try:
        author = getpass.getuser()
    except Exception:
        author = "SEAS"

    metadata = {
        "version": "1.0",
        "exported": datetime.now().isoformat(),
        "author": author,
        "total": len(instincts),
        "filter": _build_filter_description(args),
    }

    output = {"instincts": instincts, "metadata": metadata}

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(output, indent=2))
        metadata["file"] = str(out_path)
        print(f"Exported {len(instincts)} instincts to {out_path}")
    else:
        print(json.dumps(output, indent=2))

    _print_export_report(instincts, metadata)

    return 0


def cmd_instincts_report(args: argparse.Namespace) -> int:
    """Print instinct summary report (no JSON output)."""
    capabilities = load_json(CAPABILITIES_MEMORY)
    validations = load_json(VALIDATION_HISTORY)

    instincts = [_build_instinct(c, validations) for c in capabilities]

    # Apply filters
    if args.min_confidence is not None:
        instincts = [i for i in instincts if i["confidence"] >= args.min_confidence]
    if args.category:
        instincts = [i for i in instincts if i["category"] == args.category]

    metadata = {
        "total": len(instincts),
        "filter": _build_filter_description(args),
        "file": "stdout",
    }

    _print_export_report(instincts, metadata)

    return 0


def cmd_instincts_persona_list(args: argparse.Namespace) -> int:
    """List current persona constraints."""
    if load_constraints is None:
        print("[error] persona distiller not available (system module not importable)")
        return 1

    constraints = load_constraints(PERSONA_CONSTRAINTS)
    if not constraints:
        print("No persona constraints found.")
        if not PERSONA_CONSTRAINTS.exists():
            print(f"Run 'ai-self-reflection promote' to generate persona constraints.")
        return 0

    print(f"\nPersona Constraints ({len(constraints)} total)\n{'=' * 60}")
    for c in constraints:
        print(f"\n  ID: {c.id}")
        print(f"  Trigger: {c.trigger}")
        print(f"  Confidence: {c.confidence:.2f}")
        print(f"  Applied: {c.applied_count}x")
        print(f"  Sources: {', '.join(c.source_capabilities)}")
        print(f"  Constraint: {c.constraint[:120]}{'...' if len(c.constraint) > 120 else ''}")
    return 0


def cmd_instincts_persona_apply(args: argparse.Namespace) -> int:
    """Output persona constraints block for injection into a prompt."""
    if build_constraints_block is None:
        print("[error] persona distiller not available (system module not importable)")
        return 1

    block = build_constraints_block(
        scope=args.scope,
        path=PERSONA_CONSTRAINTS,
        max_tokens=args.budget,
    )

    if not block:
        print("No matching persona constraints for this scope.")
        return 0

    if args.output:
        Path(args.output).write_text(block)
        print(f"Persona constraints block written to {args.output}")
    else:
        print(block)

    return 0


def cmd_instincts_persona_distill(args: argparse.Namespace) -> int:
    """Run persona distillation from capabilities memory."""
    if distill_persona is None:
        print("[error] persona distiller not available (system module not importable)")
        return 1

    constraints = distill_persona(
        capabilities_path=CAPABILITIES_MEMORY,
        output_path=PERSONA_CONSTRAINTS,
    )

    if constraints:
        print(f"Distilled {len(constraints)} persona constraints → {PERSONA_CONSTRAINTS}")
        for c in constraints:
            print(f"  - [{c.id}] {c.trigger}: {c.constraint[:80]}")
    else:
        print("No level-3 capabilities with validation_score > 0.7 found for distillation.")
        print(f"  Need at least {2} qualifying capabilities (min_level=3, min_score=0.7).")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-self-reflection-comprehensive",
        description="Comprehensive mode: persistent learning across sessions",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # initialize
    init_p = subparsers.add_parser("initialize", help="Initialize memory structure")
    init_p.add_argument("--force", action="store_true", help="Reset existing files")

    # record
    record_p = subparsers.add_parser("record", help="Record reflection event")
    record_p.add_argument("--task", required=True)
    record_p.add_argument(
        "--category",
        required=True,
        choices=["structural", "epistemic", "interaction", "strategy"],
    )
    record_p.add_argument("--observation", required=True)
    record_p.add_argument("--friction", required=True)
    record_p.add_argument("--root-cause", required=True, dest="root_cause")
    record_p.add_argument("--lesson", required=True)
    record_p.add_argument("--scope", required=True)
    record_p.add_argument("--confidence", type=float, required=True)
    record_p.add_argument("--evidence", type=int, required=True)
    record_p.add_argument("--action", required=True)

    # distill
    distill_p = subparsers.add_parser(
        "distill", help="Distill experiences → candidate lessons"
    )
    distill_p.add_argument(
        "--min-evidence", type=int, default=2, help="Minimum observations to promote"
    )

    # promote
    promote_p = subparsers.add_parser("promote", help="Promote validated candidates")

    # validate
    validate_p = subparsers.add_parser("validate", help="Record capability validation")
    validate_p.add_argument(
        "--capability", required=True, help="Capability lesson name"
    )
    validate_p.add_argument("--task", required=True)
    validate_p.add_argument("--outcome", required=True)
    validate_p.add_argument("--success", action="store_true")
    validate_p.add_argument("--failure", dest="success", action="store_false")
    validate_p.add_argument(
        "--delta", type=float, default=0.05, help="Confidence adjustment"
    )
    validate_p.set_defaults(success=True)

    # report
    subparsers.add_parser("report", help="Generate system report")

    # bridge
    bridge_p = subparsers.add_parser(
        "bridge", help="Generate capability bridge constraints"
    )
    bridge_p.add_argument("--scope", default="general")
    bridge_p.add_argument("--budget", type=int, default=500)

    # prune
    prune_p = subparsers.add_parser("prune", help="Prune old memory records")
    prune_p.add_argument("--limit", type=int, default=500)

    # instincts
    instincts_p = subparsers.add_parser("instincts", help="Export learned instincts")
    instincts_sub = instincts_p.add_subparsers(dest="instinct_command", required=True)

    # instincts export
    export_p = instincts_sub.add_parser(
        "export", help="Export validated capabilities as instincts"
    )
    export_p.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Minimum confidence threshold (e.g. 0.8)",
    )
    export_p.add_argument(
        "--category",
        default=None,
        help="Filter by category (structural, epistemic, interaction, strategy)",
    )
    export_p.add_argument(
        "--output", default=None, help="Output file path for JSON export"
    )

    # instincts report
    report_p = instincts_sub.add_parser("report", help="Print instinct summary report")
    report_p.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Minimum confidence threshold (e.g. 0.8)",
    )
    report_p.add_argument("--category", default=None, help="Filter by category")

    # instincts persona
    persona_p = instincts_sub.add_parser("persona", help="Manage persona constraints")
    persona_sub = persona_p.add_subparsers(dest="persona_command", required=True)

    # instincts persona list
    persona_list_p = persona_sub.add_parser(
        "list", help="List current persona constraints"
    )

    # instincts persona apply
    persona_apply_p = persona_sub.add_parser(
        "apply", help="Output persona constraints block for prompt injection"
    )
    persona_apply_p.add_argument(
        "--scope", default="general", help="Scope to filter constraints by"
    )
    persona_apply_p.add_argument(
        "--budget", type=int, default=500, help="Max tokens for constraints block"
    )
    persona_apply_p.add_argument("--output", default=None, help="Output file path")

    # instincts persona distill
    persona_distill_p = persona_sub.add_parser(
        "distill", help="Run persona distillation from capabilities memory"
    )

    args = parser.parse_args()

    handlers = {
        "initialize": cmd_initialize,
        "record": cmd_record,
        "distill": cmd_distill,
        "promote": cmd_promote,
        "validate": cmd_validate,
        "report": cmd_report,
        "bridge": cmd_bridge,
        "prune": cmd_prune,
    }

    if args.command == "instincts":
        instinct_handlers = {
            "export": cmd_instincts_export,
            "report": cmd_instincts_report,
        }
        if args.instinct_command == "persona":
            persona_handlers = {
                "list": cmd_instincts_persona_list,
                "apply": cmd_instincts_persona_apply,
                "distill": cmd_instincts_persona_distill,
            }
            return persona_handlers[args.persona_command](args)
        return instinct_handlers[args.instinct_command](args)

    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
