#!/usr/bin/env python3
"""CLI tool for the AI Self-Reflection skill.

Provides interactive pre-flight checklists and post-hoc friction log
entry generation to operationalize the reflection protocol.
"""

import argparse
import sys
from datetime import date
from pathlib import Path


FRICTION_LOG = Path(__file__).resolve().parent.parent / "friction_log.md"

PREFLIGHT_QUESTIONS = [
    "What form does this answer actually need? (Paragraph? Code? Table? Diagram?)",
    "Am I defaulting to a structure because it's habitual or because it serves the content?",
    "Is there a part of this I'm uncertain about? If yes, am I planning to acknowledge that or hide it?",
    "What would I write if I had no template to fall back on?",
]

POSTHOC_QUESTIONS = [
    "Did any friction spike during this task? Where?",
    "Did I produce any output that felt performative rather than useful?",
    "Did I notice any accidental elegance in the input that I didn't surface? Should I have?",
]

ENTRY_TEMPLATE = """\n## {date} — {task}\n\n**Friction:** {friction}\n**Root cause:** {root_cause}\n**Fix for next time:** {fix}\n"""


def cmd_preflight(_args: argparse.Namespace) -> None:
    """Run the 4-question pre-flight checklist as interactive prompts."""
    print("=== Pre-flight Checklist ===")
    print("Answer these honestly — internally, not in your output.\n")

    for i, question in enumerate(PREFLIGHT_QUESTIONS, 1):
        print(f"  {i}. {question}")
        try:
            input("     [press Enter when done thinking] ")
        except (EOFError, KeyboardInterrupt):
            print("\n\nPreflight interrupted.")
            sys.exit(0)

    print("\nChecklist complete. Proceed with your response.")


def _append_to_log(text: str) -> None:
    """Append *text* to the friction log, creating the file if needed."""
    if not FRICTION_LOG.exists():
        FRICTION_LOG.write_text(f"# Friction Log\n{text}", encoding="utf-8")
    else:
        with FRICTION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(text)


def cmd_posthoc(args: argparse.Namespace) -> None:
    """Generate a friction log entry template and append it to friction_log.md."""
    task = args.task
    today = date.today().isoformat()

    print("=== Post-hoc Review ===")
    print("Answer briefly — 2-3 sentences max.\n")

    friction = input("  Friction (what felt off)? ").strip()
    root_cause = input("  Root cause (pattern or misalignment)? ").strip()
    fix = input("  Fix for next time? ").strip()

    entry = ENTRY_TEMPLATE.format(
        date=today,
        task=task,
        friction=friction or "[describe friction spike]",
        root_cause=root_cause or "[identify pattern]",
        fix=fix or "[one concrete adjustment]",
    )

    _append_to_log(entry)
    print(f"\nEntry appended to {FRICTION_LOG}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Self-Reflection CLI — preflight checklists and friction logging.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight", help="Run the 4-question pre-flight checklist")

    posthoc_p = sub.add_parser("posthoc", help="Log a post-hoc friction entry")
    posthoc_p.add_argument(
        "--task", required=True, help='Short task description (e.g. "API integration")',
    )

    args = parser.parse_args()

    if args.command == "preflight":
        cmd_preflight(args)
    elif args.command == "posthoc":
        cmd_posthoc(args)


if __name__ == "__main__":
    main()
