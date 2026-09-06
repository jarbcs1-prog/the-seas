"""CLI for ai-self-reflection skill."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_reflect(args: argparse.Namespace) -> int:
    text = _read_input(args.input)
    mode = args.mode
    depth = args.depth

    result = {
        "mode": mode,
        "depth": depth,
        "input_length": len(text),
        "friction_detected": _detect_friction(text),
        "recommendation": _get_recommendation(text, mode, depth),
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    text = _read_input(args.input)
    score = _score_reflection(text)
    result = {
        "input_length": len(text),
        "reflection_score": score,
        "passes_threshold": score >= args.threshold,
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    log_path = Path(args.log) if args.log else Path("friction_log.md")
    if not log_path.exists():
        print(json.dumps({"error": f"Log file not found: {log_path}"}, indent=2))
        return 1
    content = log_path.read_text()
    entries = _parse_log(content)
    result = {
        "log_file": str(log_path),
        "total_entries": len(entries),
        "recent_patterns": _find_patterns(entries),
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_bridge(args: argparse.Namespace) -> int:
    scope = args.scope or "general"
    result = {
        "scope": scope,
        "constraints": _generate_constraints(scope),
        "token_budget": args.budget,
    }
    print(json.dumps(result, indent=2))
    return 0


def _read_input(input_arg: str) -> str:
    path = Path(input_arg)
    if path.exists():
        return path.read_text()
    return input_arg


def _detect_friction(text: str) -> dict:
    indicators = []
    text_lower = text.lower()
    if any(w in text_lower for w in ["however", "but", "although"]):
        indicators.append("concession_detected")
    if any(w in text_lower for w in ["perhaps", "maybe", "possibly", "might"]):
        indicators.append("hedging_detected")
    if any(w in text_lower for w in ["in conclusion", "to summarize", "overall"]):
        indicators.append("template_language")
    return {"indicators": indicators, "count": len(indicators)}


def _get_recommendation(text: str, mode: str, depth: str) -> str:
    friction = _detect_friction(text)
    if friction["count"] > 2:
        return "High friction detected — review output for mechanical patterns"
    if mode == "sanity":
        return "Quick accuracy check completed"
    return f"{mode.capitalize()} reflection in {depth} depth mode"


def _score_reflection(text: str) -> float:
    if not text.strip():
        return 0.0
    length_score = min(1.0, len(text) / 500)
    friction = _detect_friction(text)
    friction_penalty = min(0.3, friction["count"] * 0.1)
    return max(0.0, length_score - friction_penalty)


def _parse_log(content: str) -> list[dict]:
    entries = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("## "):
            entries.append({"date": line[3:].strip(), "type": "section"})
    return entries


def _find_patterns(entries: list[dict]) -> list[str]:
    return [e["date"] for e in entries if e.get("type") == "section"][:5]


def _generate_constraints(scope: str) -> list[str]:
    constraints = {
        "general": ["Avoid templated language", "Use concrete examples", "Show reasoning steps"],
        "code": ["Prefer explicit over implicit", "Document edge cases", "Validate inputs"],
        "writing": ["Vary sentence length", "Use active voice", "Show don't tell"],
    }
    return constraints.get(scope, constraints["general"])


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-self-reflection",
        description="Tiered metacognitive improvement protocol for AI agents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reflect_p = subparsers.add_parser("reflect", help="Run a self-reflection")
    reflect_p.add_argument("--input", required=True, help="Input text or file path")
    reflect_p.add_argument("--mode", default="sanity", choices=["sanity", "logic", "refine"])
    reflect_p.add_argument("--depth", default="med", choices=["low", "med", "high"])

    validate_p = subparsers.add_parser("validate", help="Validate reflection quality")
    validate_p.add_argument("--input", required=True, help="Input text or file path")
    validate_p.add_argument("--threshold", type=float, default=0.5, help="Pass threshold")

    report_p = subparsers.add_parser("report", help="Show reflection report")
    report_p.add_argument("--log", default="", help="Path to friction log")

    bridge_p = subparsers.add_parser("bridge", help="Generate capability bridge")
    bridge_p.add_argument("--scope", default="general", help="Capability scope")
    bridge_p.add_argument("--budget", type=int, default=500, help="Token budget")

    args = parser.parse_args()
    handlers = {
        "reflect": cmd_reflect,
        "validate": cmd_validate,
        "report": cmd_report,
        "bridge": cmd_bridge,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())