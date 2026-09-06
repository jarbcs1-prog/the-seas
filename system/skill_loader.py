"""Skill loader — discovers, parses and loads SKILL.md files from the skills directory.

Scans ``skills/`` for directories containing ``SKILL.md``, extracts YAML frontmatter
(name, description, triggers) and makes the markdown body available for instruction
loading.  Also supports legacy JSON skill definitions alongside the new SKILL.md format.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml

from .skill_writer import get_skills_dir

SKILLS_DIR = get_skills_dir()
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class SkillSpec:
    """Parsed metadata and body from a SKILL.md file."""

    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    file_path: str = ""
    body: str = ""
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    compatibility: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SkillSpec":
        return cls(**data)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and remaining body from markdown text.

    Returns
    -------
    tuple[dict, str]
        (frontmatter dict, body string without frontmatter marker)
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    body = text[match.end() :]
    return meta, body


def _load_skill_from_skilledmd(skill_dir: Path) -> Optional[SkillSpec]:
    """Load a skill from a SKILL.md file inside ``skill_dir``."""
    md_path = skill_dir / "SKILL.md"
    if not md_path.exists():
        return None
    try:
        raw = md_path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        name = meta.get("name") or skill_dir.name
        description = meta.get("description") or ""
        triggers = meta.get("triggers") or []
        tags = meta.get("tags") or []
        compatibility = meta.get("compatibility") or []
        version = meta.get("version") or "1.0.0"
        return SkillSpec(
            name=name,
            description=description,
            triggers=triggers,
            file_path=str(md_path),
            body=body,
            version=version,
            tags=tags,
            compatibility=compatibility,
        )
    except Exception as exc:
        print(f"[SkillLoader] Error parsing {md_path}: {exc}")
        return None


def _load_skill_from_json(skill_dir: Path) -> Optional[SkillSpec]:
    """Load a legacy skill from a ``<name>.json`` file inside ``skill_dir``."""
    json_path = skill_dir / f"{skill_dir.name}.json"
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return SkillSpec(
            name=data.get("name", skill_dir.name),
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            file_path=str(json_path),
            body=data.get("instructions", ""),
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            compatibility=data.get("compatibility", []),
        )
    except Exception as exc:
        print(f"[SkillLoader] Error parsing {json_path}: {exc}")
        return None


def discover_skills(skills_dir: str | Path = SKILLS_DIR) -> list[SkillSpec]:
    """Scan ``skills/`` for directories containing ``SKILL.md`` or legacy ``.json`` files.

    Returns skills sorted alphabetically by name.
    """
    base = Path(skills_dir)
    if not base.exists():
        return []
    specs: list[SkillSpec] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        spec = _load_skill_from_skilledmd(entry)
        if spec is None:
            spec = _load_skill_from_json(entry)
        if spec is not None:
            specs.append(spec)
    return specs


def load_skill(name: str, skills_dir: str | Path = SKILLS_DIR) -> Optional[SkillSpec]:
    """Load a single skill by name, searching ``skills/`` for a matching directory."""
    base = Path(skills_dir)
    if not base.exists():
        return None
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name != name:
            continue
        spec = _load_skill_from_skilledmd(entry)
        if spec is None:
            spec = _load_skill_from_json(entry)
        return spec
    return None


def load_all(skills_dir: str | Path = SKILLS_DIR) -> list[SkillSpec]:
    """Load all discoverable skills."""
    return discover_skills(skills_dir)


def find_by_trigger(text: str, skills_dir: str | Path = SKILLS_DIR) -> list[SkillSpec]:
    """Find skills whose triggers match keywords in the given text."""
    text_lower = text.lower()
    results: list[SkillSpec] = []
    for spec in discover_skills(skills_dir):
        for trigger in spec.triggers:
            if trigger.lower() in text_lower:
                results.append(spec)
                break
    return results


def find_by_tag(tag: str, skills_dir: str | Path = SKILLS_DIR) -> list[SkillSpec]:
    """Find skills that have a given tag."""
    tag_lower = tag.lower()
    return [s for s in discover_skills(skills_dir) if tag_lower in [t.lower() for t in s.tags]]


def validate_skill(spec: SkillSpec) -> list[str]:
    """Validate a skill spec and return a list of issues (empty if valid)."""
    issues: list[str] = []
    if not spec.name:
        issues.append("Missing 'name' in frontmatter")
    if not spec.description:
        issues.append("Missing 'description' in frontmatter")
    if not spec.file_path:
        issues.append("No SKILL.md or JSON file found")
    if not spec.body.strip():
        issues.append("SKILL.md body is empty")
    if not spec.triggers:
        issues.append("No triggers defined in frontmatter")
    return issues


def search_skills(query: str, skills_dir: str | Path = SKILLS_DIR) -> list[dict]:
    """Search skills by name, description, tags, or body (case-insensitive)."""
    q = (query or "").lower().strip()
    if not q:
        return []
    results: list[SkillSpec] = []
    for spec in discover_skills(skills_dir):
        haystack = " ".join([
            spec.name or "",
            spec.description or "",
            " ".join(spec.tags or []),
            spec.body or "",
        ]).lower()
        if q in haystack:
            results.append(spec)
    return [s.to_dict() for s in results]


def build_registry(skills_dir: str | Path = SKILLS_DIR) -> dict:
    """Build a registry dictionary of all discovered skills with metadata."""
    specs = discover_skills(skills_dir)
    return {
        "version": "1.0.0",
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "skills_dir": str(skills_dir),
        "total_skills": len(specs),
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "tags": s.tags,
                "version": s.version,
                "file_path": s.file_path,
                "compatibility": s.compatibility,
            }
            for s in specs
        ],
    }