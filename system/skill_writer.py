# system/skill_writer.py
"""Safe create/update/delete of skill SKILL.md definitions."""
from __future__ import annotations

import inspect
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

# Skills live at the repo root (F:\theseas\skills), matching where the loader,
# API and UI read them from. Do NOT point this at system/skills.
_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
from .paths import get_data_dir

HISTORY_DIR = get_data_dir() / "skill_history"


def get_skills_dir() -> Path:
    """Resolve the skills directory with precedence: SEAS_SKILLS_DIR env var -> config -> default."""
    env_dir = os.environ.get("SEAS_SKILLS_DIR")
    if env_dir:
        p = Path(env_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    # Config fallback could be added here if a config system exists
    # For now, fall back to default
    _DEFAULT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_SKILLS_DIR


# Backward-compatible module-level SKILLS_DIR that uses the resolver
SKILLS_DIR = get_skills_dir()

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError("Invalid skill name; use lowercase letters, digits, underscores")


def _skill_dir(name: str) -> Path:
    d = (SKILLS_DIR / name).resolve()
    if not str(d).startswith(str(SKILLS_DIR.resolve()) + os.sep):
        raise ValueError("Path traversal detected")
    return d


def _render(front: dict[str, Any], body: str) -> str:
    import yaml

    fm = yaml.safe_dump(front, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{fm}\n---\n\n{body}\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _scaffold_handler(path: Path, name: str) -> None:
    path.write_text(
        f'"""Auto-scaffolded handler for skill {name}. Edit externally."""\n'
        "\n\n\ndef execute(**kwargs):\n"
        '    raise NotImplementedError("Implement this handler externally")\n',
        encoding="utf-8",
    )


def _read_spec(name: str) -> dict[str, Any]:
    d = _skill_dir(name)
    if not d.exists():
        raise FileNotFoundError(f"Skill '{name}' not found")
    text = (d / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        import yaml

        front = yaml.safe_load(fm) or {}
        if not isinstance(front, dict):
            front = {}
        front["body"] = body.strip()
        return front
    return {"name": name, "body": text.strip()}


def create_skill(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    _validate_name(name)
    d = _skill_dir(name)
    if d.exists():
        raise FileExistsError(f"Skill '{name}' already exists")
    d.mkdir(parents=True)
    body = spec.get("body", "")
    front = {k: v for k, v in spec.items() if k not in ("body", "name", "code_backed")}
    front["name"] = name
    content = _render(front, body)
    _atomic_write(d / "SKILL.md", content)
    try:
        from . import skill_history

        skill_history.snapshot(name, content)
    except Exception:
        pass
    if spec.get("code_backed"):
        _scaffold_handler(d / "handler.py", name)
    return _read_spec(name)


def update_skill(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    _validate_name(name)
    d = _skill_dir(name)
    if not d.exists():
        raise FileNotFoundError(f"Skill '{name}' not found")
    prev = (d / "SKILL.md").read_text(encoding="utf-8")
    body = spec.get("body", "")
    front = {k: v for k, v in spec.items() if k not in ("body", "name", "code_backed")}
    front["name"] = name
    content = _render(front, body)
    try:
        from . import skill_history

        skill_history.snapshot(name, prev)
    except Exception:
        pass
    _atomic_write(d / "SKILL.md", content)
    return _read_spec(name)


def delete_skill(name: str) -> None:
    _validate_name(name)
    d = _skill_dir(name)
    if not d.exists():
        raise FileNotFoundError(f"Skill '{name}' not found")
    shutil.rmtree(d)


def backfill_skill_inputs() -> int:
    """Introspect handler signatures of code-backed skills and write `inputs` frontmatter.

    Uses a SkillRegistry instance (get_handler is an instance method, not a
    module-level function) with CRM handlers registered. Best-effort per skill:
    a failure on one skill is logged and skipped so it cannot block the others.
    """
    from . import skill_registry

    reg = skill_registry.SkillRegistry(SKILLS_DIR)
    reg.register_crm_skill_handlers()

    count = 0
    for p in SKILLS_DIR.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        try:
            handler = reg.get_handler(name)
            if handler is None:
                continue
            try:
                sig = inspect.signature(handler)
            except (ValueError, TypeError):
                continue
            inputs = []
            for pname, param in sig.parameters.items():
                if pname in ("self", "args", "kwargs"):
                    continue
                required = param.default is inspect.Parameter.empty
                inputs.append(
                    {
                        "name": pname,
                        "type": "string",
                        "required": required,
                        "default": None if required else param.default,
                    }
                )
            if inputs:
                spec = _read_spec(name)
                if not spec.get("inputs"):
                    spec["inputs"] = inputs
                    update_skill(name, spec)
                    count += 1
        except Exception as exc:  # best-effort: never abort the whole backfill
            print(f"[skill_writer] backfill_skill_inputs failed for {name}: {exc}")
            continue
    return count
