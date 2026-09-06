"""Skill registry — discovers, loads and matches skills for task execution.

Each skill defines a named capability with triggers, tags and an optional
handler reference. The registry provides dynamic loading and matching.

Supports both legacy JSON skill definitions (``<name>.json``) and the new
SKILL.md format (YAML frontmatter in ``<name>/SKILL.md``).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import yaml

from .models import Task
from .skill_writer import get_skills_dir


SKILLS_DIR = get_skills_dir()
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# CRM skill handlers — ported from the Eve/CRM TypeScript codebase (see
# docs/CRM_INTEGRATION.md). Each maps to skills/<name>/handler.py which exposes
# an `execute` function. Repo-only skills are always available; external-source
# skills gate on their API-key capability at call time.
CRM_SKILL_HANDLER_MODULES = [
    "crm_search", "crm_dossier", "crm_enrich", "crm_record_fact", "crm_history",
    "crm_lookup_socials", "crm_perplexity", "crm_linkedin", "crm_company",
    "crm_contact", "crm_meetings", "crm_threads", "crm_deals", "crm_evidence",
    "crm_brand", "crm_facts", "crm_names", "crm_tasks",
]


def _import_crm_handler(module_name: str):
    """Import the `execute` callable from a CRM skill's handler module."""
    import importlib

    module = importlib.import_module(f"skills.{module_name}.handler")
    return getattr(module, "execute", None)


def _parse_skillmd_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and remaining body from markdown text."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    body = text[match.end() :]
    return meta, body


@dataclass
class Skill:
    """A named capability with triggers, tags and handler info."""

    name: str
    description: str
    skill_tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)  # Keywords that activate this skill
    handler_module: str = ""    # Python module path (e.g.  "skills.my_skill.handler")
    handler_func: str = ""      # Handler function name
    config: dict = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)  # Dependencies (other skills/tools)
    risk_level: str = "low"     # Default risk level when using this skill
    cost_multiplier: float = 1.0  # Cost scaling factor
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(**data)

    @classmethod
    def from_skilledmd(cls, skill_dir: Path) -> Optional["Skill"]:
        """Load a Skill from a SKILL.md file inside ``skill_dir``."""
        md_path = skill_dir / "SKILL.md"
        if not md_path.exists():
            return None
        try:
            raw = md_path.read_text(encoding="utf-8")
            meta, body = _parse_skillmd_frontmatter(raw)
            name = meta.get("name") or skill_dir.name
            description = meta.get("description") or ""
            triggers = meta.get("triggers") or []
            tags = meta.get("tags") or []
            return cls(
                name=name,
                description=description,
                skill_tags=tags,
                triggers=triggers,
                handler_module="",
                handler_func="",
                config={"body": body, "file_path": str(md_path)},
            )
        except Exception as exc:
            print(f"[SkillRegistry] Error loading SKILL.md {md_path}: {exc}")
            return None


class SkillRegistry:
    """Manages skill discovery, loading and matching.

    Supports both legacy JSON skill definitions (``<name>.json``) and the new
    SKILL.md format (YAML frontmatter in ``<name>/SKILL.md``).
    """

    def __init__(self, skills_dir: str | Path = SKILLS_DIR):
        self.skills_dir = Path(skills_dir)
        self._cache: dict[str, Skill] = {}
        self._handlers: dict[str, Callable] = {}

    def discover(self) -> list[str]:
        """Scan skills directory and return available skill names.

        Supports both legacy JSON files (``<name>.json``) and the new
        SKILL.md format (directories containing ``<name>/SKILL.md``).
        """
        if not self.skills_dir.exists():
            return []
        names: list[str] = []
        # JSON-based skills (legacy) — skip registry.json and other non-skill files
        for path in sorted(self.skills_dir.glob("*.json")):
            if path.name == "registry.json":
                continue
            names.append(path.stem)
        # Directory-based SKILL.md skills
        for path in sorted(self.skills_dir.iterdir()):
            if path.is_dir() and (path / "SKILL.md").exists():
                if path.name not in names:
                    names.append(path.name)
        return sorted(names)

    def load(self, name: str) -> Optional[Skill]:
        """Load a single skill by name.

        Checks for SKILL.md in a directory first, then falls back to JSON.
        """
        if name in self._cache:
            return self._cache[name]

        # Try SKILL.md in directory first
        dir_path = self.skills_dir / name
        if dir_path.is_dir():
            skill = Skill.from_skilledmd(dir_path)
            if skill is not None:
                self._cache[name] = skill
                return skill

        # Try JSON (legacy)
        json_path = self.skills_dir / f"{name}.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                skill = Skill.from_dict(data)
                self._cache[name] = skill
                return skill
            except (json.JSONDecodeError, IOError, KeyError) as e:
                print(f"[SkillRegistry] Error loading {name}: {e}")
                return None

        return None

    def load_all(self) -> list[Skill]:
        """Load all available skills."""
        skills = []
        for name in self.discover():
            skill = self.load(name)
            if skill:
                skills.append(skill)
        return skills

    def save(self, skill: Skill) -> bool:
        """Save a skill definition to disk."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        skill.updated_at = datetime.now().isoformat()
        path = self.skills_dir / f"{skill.name}.json"
        try:
            path.write_text(
                json.dumps(skill.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._cache[skill.name] = skill
            return True
        except IOError as e:
            print(f"[SkillRegistry] Error saving {skill.name}: {e}")
            return False

    def find_by_tag(self, tag: str) -> list[Skill]:
        """Find all skills that have a given skill_tag."""
        return [s for s in self.load_all() if tag in s.skill_tags]

    def find_by_trigger(self, text: str) -> list[Skill]:
        """Find skills whose triggers match keywords in the given text."""
        text_lower = text.lower()
        matches = []
        for skill in self.load_all():
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    matches.append(skill)
                    break
        return matches

    def match_task(self, task: Task) -> list[Skill]:
        """Find skills that best match a task's skill_tags.

        Returns skills sorted by relevance (most matching tags first).
        """
        if not task.skill_tags:
            return []

        task_tags = set(tag.lower() for tag in task.skill_tags)
        scored: list[tuple[int, Skill]] = []

        for skill in self.load_all():
            skill_tags = set(tag.lower() for tag in skill.skill_tags)
            matches = len(task_tags & skill_tags)
            if matches > 0:
                scored.append((matches, skill))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored]

    def register_handler(self, skill_name: str, handler: Callable):
        """Register a Python handler function for a skill."""
        self._handlers[skill_name] = handler

    def get_handler(self, skill_name: str) -> Optional[Callable]:
        """Get a registered handler for a skill."""
        return self._handlers.get(skill_name)

    def register_crm_skill_handlers(self) -> int:
        """Import and register handlers for all ported CRM skills.

        Returns the number of handlers successfully registered. A failure to
        import one skill is logged and skipped so it cannot block the others.
        """
        registered = 0
        for name in CRM_SKILL_HANDLER_MODULES:
            try:
                handler = _import_crm_handler(name)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[SkillRegistry] Could not import CRM handler {name}: {exc}")
                continue
            if handler is not None:
                self.register_handler(name, handler)
                registered += 1
        return registered

    def clear_cache(self):
        """Clear the skill cache (forces re-read from disk)."""
        self._cache.clear()

    def create_default_skills(self) -> list[Skill]:
        """Create and save a set of default built-in skills.

        These cover the common execution patterns used by profiles.
        """
        defaults = [
            Skill(
                name="goal-decomposition",
                description="Break a high-level goal into a structured task graph with dependencies and verification gates.",
                skill_tags=["planning", "decomposition", "architecture"],
                triggers=["decompose", "break down", "task graph", "plan"],
                risk_level="low",
                cost_multiplier=0.8,
            ),
            Skill(
                name="code-implementation",
                description="Write, modify or refactor code to implement a specified feature or fix.",
                skill_tags=["execution", "implementation", "coding", "building"],
                triggers=["implement", "write code", "build", "create file", "add feature"],
                risk_level="medium",
                cost_multiplier=1.2,
            ),
            Skill(
                name="code-review",
                description="Review code for correctness, style, security and best practices.",
                skill_tags=["review", "verification", "quality", "testing"],
                triggers=["review", "audit", "check code", "inspect"],
                risk_level="low",
                cost_multiplier=0.5,
            ),
            Skill(
                name="testing",
                description="Write and run tests (unit, integration, e2e) to validate correctness.",
                skill_tags=["testing", "verification", "quality"],
                triggers=["test", "write tests", "pytest", "unit test"],
                risk_level="low",
                cost_multiplier=0.6,
            ),
            Skill(
                name="research-investigation",
                description="Search, gather and synthesize information from web and local sources.",
                skill_tags=["research", "analysis", "investigation", "synthesis"],
                triggers=["research", "investigate", "search", "find out", "explore"],
                risk_level="low",
                cost_multiplier=0.9,
            ),
            Skill(
                name="documentation",
                description="Write clear, structured documentation including README, API docs and guides.",
                skill_tags=["writing", "documentation", "communication"],
                triggers=["document", "write docs", "readme", "documentation"],
                risk_level="low",
                cost_multiplier=0.5,
            ),
            Skill(
                name="debugging",
                description="Diagnose and fix issues in code, configuration or systems.",
                skill_tags=["debugging", "analysis", "fixing"],
                triggers=["debug", "fix bug", "error", "issue", "not working"],
                risk_level="medium",
                cost_multiplier=1.0,
            ),
            Skill(
                name="deployment",
                description="Prepare, stage and deploy applications to target environments.",
                skill_tags=["devops", "deployment", "infrastructure"],
                triggers=["deploy", "release", "publish", "ship", "production"],
                risk_level="high",
                cost_multiplier=1.5,
            ),
        ]

        created = []
        for skill in defaults:
            path = self.skills_dir / f"{skill.name}.json"
            if not path.exists():
                self.save(skill)
                created.append(skill)
            else:
                loaded = self.load(skill.name)
                if loaded:
                    created.append(loaded)

        return created

    def get_stats(self) -> dict:
        """Get registry statistics."""
        skills = self.load_all()
        tags = {}
        for s in skills:
            for tag in s.skill_tags:
                tags[tag] = tags.get(tag, 0) + 1
        return {
            "total_skills": len(skills),
            "tags": dict(sorted(tags.items(), key=lambda x: -x[1])),
            "cached": len(self._cache),
            "handlers_registered": len(self._handlers),
        }
