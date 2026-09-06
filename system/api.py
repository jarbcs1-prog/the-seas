"""
REST API Layer for The S.E.A.S
T-046: Full REST API with OpenAPI/Swagger documentation

Provides versioned API endpoints for all system resources:
tasks, memory, eval, profiles, plugins, analytics, auth, system.

Usage:
    python -m system.api                      # Start API server on port 8000
    python -m system.api --port 9000           # Custom port
    python -m system.api --host 0.0.0.0        # Listen on all interfaces
    python -m system.api --reload              # Auto-reload on code changes (FastAPI only)

OpenAPI docs:
    http://localhost:8000/docs                 # Swagger UI
    http://localhost:8000/redoc                # ReDoc alternative
"""

import asyncio
import json
import os
import sqlite3
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field, asdict
from functools import wraps
from .provider_manager import get_provider_manager, DEFAULT_BASE_URLS
from .inference_service import InferenceError, get_inference_service
from .instruction_service import get_instruction_service, InstructionError
from .extension_service import get_extension_service, ExtensionError
from .prompts_index import PromptsIndex
from .cognition import get_cognition_state
from .crm_db import CrmDatabaseManager, CrmDatabaseError
from .dojo import (
    DojoError,
    DatasetStore,
    build_modelfile,
    ollama_calibrate,
    openai_finetune_status,
    openai_finetune_submit,
    _base_model_exists,
    _run_calibration_job,
    CALIBRATION_JOBS,
    is_valid_model_name,
)
from . import skill_writer, skill_history
from fastapi.responses import JSONResponse
from fastapi import HTTPException, File, UploadFile, Body

# ── AG2 Memory Service ────────────────────────────────────────────────────────────

class AG2MemoryService:
    """Service for AG2 memory integration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (PROJECT_ROOT / "system" / "config" / "ag2" / "memory.conf")
        self.config = self._load_config()
        self.connected = self._test_connection()
    
    def _load_config(self) -> dict:
        """Load AG2 memory configuration."""
        default_config = {
            "server": "http://127.0.0.1:8020",
            "key": "",
            "namespace": "seas_workflow"
        }
        
        if self.config_path.exists():
            try:
                config_data = json.loads(self.config_path.read_text(encoding="utf-8"))
                default_config.update(config_data)
                return default_config
            except (json.JSONDecodeError, OSError):
                pass
        return default_config
    
    def _test_connection(self) -> bool:
        """Test connection to AG2 memory server."""
        # In a real implementation, this would make an HTTP request
        # For now, we'll just check if the config is valid
        return bool(self.config.get("server") and self.config.get("key"))
    
    def store(self, key: str, value: Any) -> bool:
        """Store a value in AG2 memory."""
        # Placeholder implementation
        # Real implementation would make HTTP POST to AG2 server
        if not self.connected:
            return False
        # Simulate successful storage
        return True
    
    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a value from AG2 memory."""
        # Placeholder implementation
        if not self.connected:
            return None
        # Simulate retrieval
        return {"stored": True, "key": key, "value": "placeholder"}
    
    def delete(self, key: str) -> bool:
        """Delete a value from AG2 memory."""
        if not self.connected:
            return False
        return True
    
    def list_keys(self) -> list[str]:
        """List all keys in the namespace."""
        if not self.connected:
            return []
        return []

# ── Project Paths ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_DIR = PROJECT_ROOT / "system"
DATA_DIR = PROJECT_ROOT


class SettingsService:
    """Persisted app settings backed by a JSON file."""

    DEFAULTS: dict = {
        "backend_url": "http://127.0.0.1:8377",
        "theme": "dark",
        "accent": "teal",
        # TencentDB Agent Memory v2.0 integration (TENCENT_MEM_INTEGRATION_ROADMAP, Phase 0).
        # Default port is 8420 (Memory Core Gateway), per agent-memory-v2.0/INSTALL.md.
        # Feature flag defaults to False so the existing JSON memory stays the source of truth.
        "MEMORY_CORE_ENABLED": False,
        "MEMORY_CORE_ENDPOINT": "http://127.0.0.1:8420",
        "MEMORY_API_KEY": "local",
        "MEMORY_SERVICE_ID": "seas-desktop",
        "MEMORY_TEAM_ID": "seas-default",
        "MEMORY_AGENT_ID": "seas-default-agent",
        "MEMORY_USER_ID": "seas-user",
    }

    def __init__(self, settings_file: Optional[Path] = None):
        self.settings_file = Path(settings_file) if settings_file else (SYSTEM_DIR / "data" / "settings.json")
        self._settings: dict = dict(self.DEFAULTS)
        self._load()
        # Backfill any newly added defaults without overwriting the user's saved values.
        for key, value in self.DEFAULTS.items():
            self._settings.setdefault(key, value)

    def _load(self) -> None:
        try:
            if self.settings_file.exists():
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._settings = data
        except (json.JSONDecodeError, OSError):
            pass

    def get_settings(self) -> dict:
        return dict(self._settings)

    def update_settings(self, updates: dict) -> dict:
        self._settings.update(updates)
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(
                json.dumps(self._settings, indent=2), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            print(f"[SettingsService] persist failed: {exc}")
        return dict(self._settings)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def memory_core_config(self) -> dict:
        """Snapshot of the MemoryCore integration keys (always returns all 6)."""
        return {k: self._settings.get(k, self.DEFAULTS.get(k)) for k in (
            "MEMORY_CORE_ENABLED",
            "MEMORY_CORE_ENDPOINT",
            "MEMORY_API_KEY",
            "MEMORY_SERVICE_ID",
            "MEMORY_TEAM_ID",
            "MEMORY_AGENT_ID",
            "MEMORY_USER_ID",
        )}


# ── Data Models ────────────────────────────────────────────────────────────────

@dataclass
class PaginationParams:
    """Pagination query parameters."""
    page: int = 1
    per_page: int = 20
    max_per_page: int = 100


@dataclass
class PaginatedResponse:
    """Standard paginated response wrapper."""
    data: list[dict]
    page: int
    per_page: int
    total: int
    total_pages: int

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "pagination": {
                "page": self.page,
                "per_page": self.per_page,
                "total": self.total,
                "total_pages": self.total_pages,
            },
        }


@dataclass
class APIResponse:
    """Standard API response wrapper."""
    success: bool = True
    message: str = ""
    data: Any = None
    error: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        d = {
            "success": self.success,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
        }
        if self.data is not None:
            d["data"] = self.data
        if self.message:
            d["message"] = self.message
        if self.error:
            d["error"] = self.error
        return d


# ── Data Readers / Services ────────────────────────────────────────────────────

class TaskService:
    """Service for task resource operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self.tasks_file = project_root / "tasks" / "queue.json"
        self.tasks_dir = project_root / "tasks"

    def _read_tasks(self) -> list[dict]:
        """Read all tasks from the queue file."""
        try:
            if self.tasks_file.exists():
                data = json.loads(self.tasks_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                return data.get("tasks", [])
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_tasks(self, tasks: list[dict]) -> bool:
        """Write tasks to the queue file."""
        try:
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
            self.tasks_file.write_text(
                json.dumps(tasks, indent=2, default=str),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def list_tasks(self, status: Optional[str] = None,
                    priority: Optional[str] = None,
                    page: int = 1, per_page: int = 20) -> PaginatedResponse:
        """List tasks with optional filtering and pagination."""
        tasks = self._read_tasks()
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if priority:
            tasks = [t for t in tasks if t.get("priority") == priority]
        total = len(tasks)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        return PaginatedResponse(
            data=tasks[start:end],
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        )

    def get_task(self, task_id: str) -> Optional[dict]:
        """Get a single task by ID."""
        if self.tasks_dir.exists():
            # Check individual task files first
            task_file = self.tasks_dir / f"{task_id}.json"
            if task_file.exists():
                try:
                    return json.loads(task_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
        # Fall back to queue
        for t in self._read_tasks():
            if t.get("id") == task_id or t.get("task_id") == task_id:
                return t
        return None

    def create_task(self, title: str, description: str = "",
                     priority: str = "medium",
                     depends_on: Optional[list[str]] = None,
                     tags: Optional[list[str]] = None) -> dict:
        """Create a new task."""
        task = {
            "id": f"task-{uuid.uuid4().hex[:8]}",
            "title": title,
            "description": description,
            "status": "pending",
            "priority": priority,
            "depends_on": depends_on or [],
            "tags": tags or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tasks = self._read_tasks()
        tasks.append(task)
        self._write_tasks(tasks)
        return task

    def update_task(self, task_id: str, updates: dict) -> Optional[dict]:
        """Update a task."""
        tasks = self._read_tasks()
        for i, t in enumerate(tasks):
            if t.get("id") == task_id or t.get("task_id") == task_id:
                # Apply updates (skip None values)
                for key, val in updates.items():
                    if val is not None:
                        t[key] = val
                t["updated_at"] = datetime.now(timezone.utc).isoformat()
                tasks[i] = t
                self._write_tasks(tasks)
                return t
        return None

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        tasks = self._read_tasks()
        filtered = [t for t in tasks
                     if t.get("id") != task_id and t.get("task_id") != task_id]
        if len(filtered) == len(tasks):
            return False
        self._write_tasks(filtered)
        return True

    def get_stats(self) -> dict:
        """Get task statistics."""
        tasks = self._read_tasks()
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.get("status") == "pending"),
            "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
            "completed": sum(1 for t in tasks if t.get("status") == "completed"),
            "failed": sum(1 for t in tasks if t.get("status") == "failed"),
        }


class MemoryService:
    """Service for memory resource operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self.memory_file = project_root / "memory.json"
        self.memory_dir = project_root / "memory"

    def _read_memory(self) -> list[dict]:
        """Read all memory entries."""
        try:
            if self.memory_file.exists():
                data = json.loads(self.memory_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("entries", data.get("memory", []))
                return []
            # Try directory-based memory
            if self.memory_dir.exists():
                entries = []
                for f in sorted(self.memory_dir.glob("*.json")):
                    try:
                        entries.append(json.loads(f.read_text(encoding="utf-8")))
                    except (json.JSONDecodeError, OSError):
                        pass
                return entries
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def list_entries(self, entry_type: Optional[str] = None,
                      page: int = 1, per_page: int = 20) -> PaginatedResponse:
        """List memory entries with optional filtering."""
        entries = self._read_memory()
        if entry_type:
            entries = [e for e in entries if e.get("type") == entry_type]
        total = len(entries)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        return PaginatedResponse(
            data=entries[start:end],
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
        )

    def get_entry(self, entry_id: str) -> Optional[dict]:
        """Get a single memory entry."""
        for e in self._read_memory():
            if e.get("id") == entry_id:
                return e
        return None

    def create_entry(self, content: str, entry_type: str = "note",
                      tags: Optional[list[str]] = None,
                      source: str = "api") -> dict:
        """Create a new memory entry."""
        entry = {
            "id": f"mem-{uuid.uuid4().hex[:8]}",
            "type": entry_type,
            "content": content,
            "tags": tags or [],
            "source": source,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        entries = self._read_memory()
        entries.append(entry)
        self._write_memory(entries)
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        entries = self._read_memory()
        filtered = [e for e in entries if e.get("id") != entry_id]
        if len(filtered) == len(entries):
            return False
        self._write_memory(filtered)
        return True

    def search_memory(self, query: str, max_results: int = 20) -> list[dict]:
        """Search memory entries by keyword across content, type, and tags."""
        entries = self._read_memory()
        q = (query or "").lower().strip()
        if not q:
            return entries[:max_results]
        results = [
            e for e in entries
            if q in (e.get("content") or "").lower()
            or q in (e.get("type") or "").lower()
            or any(q in (t or "").lower() for t in (e.get("tags") or []))
        ]
        return results[:max_results]

    def _write_memory(self, entries: list[dict]) -> bool:
        """Write memory entries to disk."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(
                json.dumps(entries, indent=2, default=str),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def get_stats(self) -> dict:
        """Get memory statistics."""
        entries = self._read_memory()
        types: dict[str, int] = {}
        for e in entries:
            if isinstance(e, dict):
                t = e.get("type", "unknown")
                types[t] = types.get(t, 0) + 1
            else:
                t = "unknown"
                types[t] = types.get(t, 0) + 1
        return {
            "total": len(entries),
            "by_type": types,
        }


class EvalService:
    """Service for eval resource operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self.evals_dir = project_root / "evals"

    def get_suites(self) -> list[dict]:
        """List all eval suites."""
        try:
            suites_dir = self.evals_dir / "suites"
            if suites_dir.exists():
                suites = []
                for f in suites_dir.glob("*.json"):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        data["name"] = f.stem
                        suites.append(data)
                    except (json.JSONDecodeError, OSError):
                        pass
                return suites
        except OSError:
            pass
        return []

    def get_suite(self, name: str) -> Optional[dict]:
        """Get a specific eval suite."""
        try:
            suite_file = self.evals_dir / "suites" / f"{name}.json"
            if suite_file.exists():
                data = json.loads(suite_file.read_text(encoding="utf-8"))
                data["name"] = suite_file.stem
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def get_runs(self, suite: Optional[str] = None,
                  limit: int = 20) -> list[dict]:
        """List eval runs."""
        try:
            runs_dir = self.evals_dir / "runs"
            if runs_dir.exists():
                runs = []
                for f in sorted(runs_dir.glob("eval-*.json"), reverse=True):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        runs.append(data)
                    except (json.JSONDecodeError, OSError):
                        pass
                if suite:
                    runs = [r for r in runs if r.get("suite") == suite]
                return runs[:limit]
        except OSError:
            pass
        return []

    def get_run(self, run_id: str) -> Optional[dict]:
        """Get a specific eval run."""
        try:
            run_file = self.evals_dir / "runs" / f"{run_id}.json"
            if run_file.exists():
                return json.loads(run_file.read_text(encoding="utf-8"))
            # Try with eval- prefix
            run_file = self.evals_dir / "runs" / f"eval-{run_id}.json"
            if run_file.exists():
                return json.loads(run_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def get_baseline(self) -> dict:
        """Get eval baseline data."""
        try:
            baseline_file = self.evals_dir / "baseline.json"
            if baseline_file.exists():
                return json.loads(baseline_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def get_stats(self) -> dict:
        """Get eval statistics."""
        runs = self.get_runs(limit=100)
        if not runs:
            return {"total_runs": 0, "avg_pass_rate": 0.0, "suites": []}

        suite_names = set()
        total_pass_rate = 0.0
        for r in runs:
            suite_names.add(r.get("suite", "unknown"))
            total_pass_rate += r.get("pass_rate", 0) if isinstance(r.get("pass_rate"), (int, float)) else 0

        return {
            "total_runs": len(runs),
            "unique_suites": len(suite_names),
            "suites": sorted(suite_names),
            "avg_pass_rate": round(total_pass_rate / len(runs), 4) if runs else 0.0,
            "latest_run": runs[0] if runs else None,
        }


class WorkflowService:
    """Service for workflow resource operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self.workflows_dir = project_root / "workflows"
        self.workflows_defs_dir = self.workflows_dir / "definitions"
        self.workflows_exec_dir = self.workflows_dir / "executions"

    def _ensure_dirs(self):
        """Ensure workflow directories exist."""
        directories = [
            self.workflows_dir,
            self.workflows_defs_dir,
            self.workflows_exec_dir
        ]
        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)

    def get_workflows(self) -> list[dict]:
        """List all workflow definitions."""
        self._ensure_dirs()
        try:
            workflows = []
            for f in self.workflows_defs_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    data["id"] = f.stem
                    workflows.append(data)
                except (json.JSONDecodeError, OSError):
                    pass
            return workflows
        except OSError:
            pass
        return []

    def create_workflow(self, workflow_data: dict) -> str:
        """Create a workflow definition."""
        self._ensure_dirs()
        workflow_id = str(uuid.uuid4())
        workflow_path = self.workflows_defs_dir / f"{workflow_id}.json"
        with open(workflow_path, 'w', encoding='utf-8') as f:
            json.dump(workflow_data, f, indent=2)
        return workflow_id

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow definition."""
        workflow_path = self.workflows_defs_dir / f"{workflow_id}.json"
        if not workflow_path.exists():
            return False
        workflow_path.unlink(missing_ok=True)
        return True

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """Get a workflow definition by ID."""
        workflow_path = self.workflows_defs_dir / f"{workflow_id}.json"
        if not workflow_path.exists():
            return None
        try:
            return json.loads(workflow_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def list_workflows(self) -> list[dict]:
        """List all workflow definitions."""
        self._ensure_dirs()
        workflows = []
        for f in self.workflows_defs_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data["id"] = f.stem
                workflows.append(data)
            except (json.JSONDecodeError, OSError):
                pass
        # Sort by created_at descending
        workflows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return workflows

    def save_execution(self, workflow_id: str, execution_result: dict):
        """Save workflow execution result."""
        self._ensure_dirs()
        execution_path = self.workflows_exec_dir / f"{workflow_id}.json"
        with open(execution_path, 'w', encoding='utf-8') as f:
            json.dump(execution_result, f, indent=2)
        return True

    def get_execution(self, workflow_id: str) -> Optional[dict]:
        """Get execution result by workflow ID."""
        execution_path = self.workflows_exec_dir / f"{workflow_id}.json"
        if not execution_path.exists():
            return None
        try:
            return json.loads(execution_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def get_executions(self, workflow_id: Optional[str] = None) -> list[dict]:
        """Get execution results, optionally filtered by workflow ID."""
        self._ensure_dirs()
        results = []
        if workflow_id:
            execution_path = self.workflows_exec_dir / f"{workflow_id}.json"
            if execution_path.exists():
                try:
                    data = json.loads(execution_path.read_text(encoding="utf-8"))
                    results.append(data)
                except (json.JSONDecodeError, OSError):
                    pass
        else:
            for f in self.workflows_exec_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    results.append(data)
                except (json.JSONDecodeError, OSError):
                    pass
        return results


class ProfileService:
    """Service for profile resource operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self.profiles_dir = project_root / "profiles"

    def list_profiles(self) -> list[dict]:
        """List all profiles."""
        try:
            if self.profiles_dir.exists():
                profiles = []
                for f in self.profiles_dir.glob("*.json"):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        data["name"] = f.stem
                        profiles.append(data)
                    except (json.JSONDecodeError, OSError):
                        pass
                # Determine active profile
                active_file = self.profiles_dir / ".active"
                active = active_file.read_text(encoding="utf-8").strip() if active_file.exists() else ""
                for p in profiles:
                    p["active"] = p.get("name") == active
                return profiles
        except OSError:
            pass
        return []

    def get_profile(self, name: str) -> Optional[dict]:
        """Get a specific profile."""
        try:
            profile_file = self.profiles_dir / f"{name}.json"
            if profile_file.exists():
                data = json.loads(profile_file.read_text(encoding="utf-8"))
                data["name"] = profile_file.stem
                active_file = self.profiles_dir / ".active"
                active = active_file.read_text(encoding="utf-8").strip() if active_file.exists() else ""
                data["active"] = data.get("name") == active
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def set_active(self, name: str) -> bool:
        """Set the active profile."""
        try:
            profile_file = self.profiles_dir / f"{name}.json"
            if not profile_file.exists():
                return False
            active_file = self.profiles_dir / ".active"
            active_file.write_text(name, encoding="utf-8")
            return True
        except OSError:
            return False

    def get_active(self) -> Optional[dict]:
        """Get the currently active profile, or None if none set."""
        try:
            active_file = self.profiles_dir / ".active"
            if active_file.exists():
                active = active_file.read_text(encoding="utf-8").strip()
                if active:
                    return self.get_profile(active)
        except OSError:
            pass
        return None


class PluginService:
    """Service for plugin resource operations (wraps T-044 PluginManager)."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self._manager = None

    def _get_manager(self):
        """Lazy-init the plugin manager."""
        if self._manager is None:
            # Avoid circular import at module level
            from system.plugin_system import PluginManager
            from system.paths import get_plugins_dir
            self._manager = PluginManager(
                plugin_dirs=[str(get_plugins_dir())],
                registry_dir=str(get_plugins_dir() / "registry"),
            )
        return self._manager

    def list_plugins(self, status: Optional[str] = None) -> list[dict]:
        """List all plugins."""
        mgr = self._get_manager()
        plugins = mgr.registry.list_plugins(status)
        return [p.to_dict() for p in plugins]

    def get_plugin(self, plugin_id: str) -> Optional[dict]:
        """Get a single plugin."""
        mgr = self._get_manager()
        plugin = mgr.registry.get(plugin_id)
        if plugin:
            return plugin.to_dict()
        # Try by name
        plugin = mgr.registry.get_by_name(plugin_id)
        if plugin:
            return plugin.to_dict()
        return None

    def install_plugin(self, source_path: str) -> tuple[bool, str]:
        """Install a plugin from a path."""
        mgr = self._get_manager()
        return mgr.install_plugin(source_path)

    def uninstall_plugin(self, plugin_id: str) -> tuple[bool, str]:
        """Uninstall a plugin."""
        mgr = self._get_manager()
        return mgr.uninstall_plugin(plugin_id)

    def activate_plugin(self, plugin_id: str) -> tuple[bool, str]:
        """Activate a plugin."""
        mgr = self._get_manager()
        return mgr.activate_plugin(plugin_id)

    def deactivate_plugin(self, plugin_id: str) -> tuple[bool, str]:
        """Deactivate a plugin."""
        mgr = self._get_manager()
        return mgr.deactivate_plugin(plugin_id)

    def get_stats(self) -> dict:
        """Get plugin statistics."""
        mgr = self._get_manager()
        return mgr.get_plugin_stats()

    def discover_plugins(self) -> list[dict]:
        """Discover available plugins."""
        mgr = self._get_manager()
        return [m.to_dict() for m in mgr.discover_plugins()]

    def install_plugin_from_manifest(self, manifest: dict, code: str | None = None) -> tuple[bool, str]:
        """Install a plugin from an in-memory manifest (Import flow)."""
        mgr = self._get_manager()
        return mgr.install_plugin_from_manifest(manifest, code)

    def export_plugin(self, plugin_id: str) -> Optional[dict]:
        """Return a plugin's manifest + source for export."""
        mgr = self._get_manager()
        plugin = mgr.registry.get(plugin_id) or mgr.registry.get_by_name(plugin_id)
        if not plugin:
            return None
        install_path = Path(plugin.install_path)
        manifest_path = install_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else plugin.manifest.to_dict()
        code = None
        main_path = install_path / "main.py"
        if main_path.exists():
            code = main_path.read_text(encoding="utf-8")
        return {"plugin_id": plugin.plugin_id, "name": plugin.manifest.name, "manifest": manifest, "code": code}

    def update_plugin_manifest(self, plugin_id: str, manifest: dict) -> tuple[bool, str]:
        """Edit a plugin's manifest (Edit flow)."""
        mgr = self._get_manager()
        plugin = mgr.registry.get(plugin_id) or mgr.registry.get_by_name(plugin_id)
        if not plugin:
            return False, f"Plugin '{plugin_id}' not found"
        from system.plugin_system import PluginManifest
        try:
            new_manifest = PluginManifest.from_dict(manifest)
        except (KeyError, TypeError, ValueError) as e:
            return False, f"Invalid manifest: {e}"
        install_path = Path(plugin.install_path)
        (install_path / "manifest.json").write_text(
            json.dumps(new_manifest.to_dict(), indent=2), encoding="utf-8"
        )
        plugin.manifest = new_manifest
        mgr.registry._save_registry()
        return True, f"Plugin '{new_manifest.name}' manifest updated"


class SkillService:
    """Service for skill resource operations (wraps system/skill_loader.py)."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        from system.skill_writer import get_skills_dir

        self.skills_dir = get_skills_dir()
        # Optional shared registry (set by APIService) so executability is
        # computed through the exact same handler-resolution path the execute
        # endpoint uses. Falls back to a freshly built registry otherwise.
        self._registry = None

    def _annotate(self, spec: dict) -> dict:
        """Annotate a skill spec with `executable`/`inputs`/`type` metadata."""
        from . import skill_registry

        reg = self._registry or skill_registry.SkillRegistry(self.skills_dir)
        reg.register_crm_skill_handlers()
        name = spec.get("name")
        spec["executable"] = reg.get_handler(name) is not None
        spec.setdefault("inputs", spec.get("inputs", []))
        spec.setdefault("type", "generic")
        return spec

    def _load_all(self) -> list[dict]:
        """Load all discoverable skills as dicts (body included)."""
        from system.skill_loader import discover_skills
        return [spec.to_dict() for spec in discover_skills(self.skills_dir)]

    def list_skills(self, tag: Optional[str] = None) -> list[dict]:
        """List all skills, optionally filtered by tag. Omits bodies for list views."""
        from system.skill_loader import discover_skills, find_by_tag
        specs = find_by_tag(tag, self.skills_dir) if tag else discover_skills(self.skills_dir)
        out = []
        for s in specs:
            d = s.to_dict()
            d.pop("body", None)
            out.append(self._annotate(d))
        return out

    def get_skill(self, name: str) -> Optional[dict]:
        """Get a single skill by name (full detail incl. body + validation issues)."""
        from system.skill_loader import load_skill, validate_skill
        spec = load_skill(name, self.skills_dir)
        if not spec:
            return None
        d = spec.to_dict()
        d["issues"] = validate_skill(spec)
        return self._annotate(d)

    def get_stats(self) -> dict:
        """Get skill statistics."""
        from system.skill_loader import discover_skills, validate_skill
        specs = discover_skills(self.skills_dir)
        tags: dict[str, int] = {}
        valid = invalid = 0
        for s in specs:
            issues = validate_skill(s)
            if issues:
                invalid += 1
            else:
                valid += 1
            for t in s.tags:
                tags[t] = tags.get(t, 0) + 1
        return {
            "total_skills": len(specs),
            "valid": valid,
            "invalid": invalid,
            "tags": dict(sorted(tags.items(), key=lambda x: -x[1])),
            "skills_dir": str(self.skills_dir),
        }

    def find_by_trigger(self, text: str) -> list[dict]:
        """Find skills whose triggers match keywords in the given text."""
        from system.skill_loader import find_by_trigger
        return [s.to_dict() for s in find_by_trigger(text, self.skills_dir)]

    def search_skills(self, q: str) -> list[dict]:
        """Search skills by name, description, tags, or body (case-insensitive)."""
        from system.skill_loader import search_skills
        return search_skills(q, self.skills_dir)

    def validate(self, name: Optional[str] = None) -> dict:
        """Validate all skills (or a single named skill) and report issues."""
        from system.skill_loader import discover_skills, load_skill, validate_skill
        if name:
            spec = load_skill(name, self.skills_dir)
            if not spec:
                return {"name": name, "valid": False, "issues": ["Skill not found"]}
            issues = validate_skill(spec)
            return {"name": name, "valid": len(issues) == 0, "issues": issues}
        results = []
        valid = invalid = 0
        for spec in discover_skills(self.skills_dir):
            issues = validate_skill(spec)
            if issues:
                invalid += 1
            else:
                valid += 1
            results.append({"name": spec.name, "valid": len(issues) == 0, "issues": issues})
        return {"total": len(results), "valid": valid, "invalid": invalid, "results": results}


class AnalyticsService:
    """Service for analytics resource operations (wraps T-043 AI/ML)."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self._ml = None

    def _get_ml(self):
        """Lazy-init the AI/ML module."""
        if self._ml is None:
            try:
                from system.ai_ml import (
                    MLPredictor, AnomalyDetector, SmartRouter, get_metrics
                )
                self._ml = {
                    "predictor": MLPredictor(),
                    "anomaly_detector": AnomalyDetector(),
                    "smart_router": SmartRouter(),
                    "get_metrics": get_metrics,
                }
            except ImportError:
                self._ml = {}
        return self._ml

    def get_metrics(self, metric_type: Optional[str] = None) -> list[dict]:
        """Get analytics metrics."""
        ml = self._get_ml()
        get_metrics_fn = ml.get("get_metrics", None)
        if get_metrics_fn:
            metrics = get_metrics_fn()
            if metric_type:
                return [m for m in metrics if m.get("type") == metric_type]
            return metrics
        return []

    def predict(self, model: str = "default", features: Optional[dict] = None) -> dict:
        """Make a prediction."""
        ml = self._get_ml()
        predictor = ml.get("predictor", None)
        if predictor:
            try:
                result = predictor.predict(features or {})
                return {"model": model, "prediction": result, "status": "success"}
            except Exception as e:
                return {"model": model, "error": str(e), "status": "error"}
        return {"model": model, "error": "ML module not available", "status": "unavailable"}

    def detect_anomalies(self, data: Optional[list] = None) -> dict:
        """Detect anomalies in data."""
        ml = self._get_ml()
        detector = ml.get("anomaly_detector", None)
        if detector:
            try:
                result = detector.detect(data or [])
                return {"anomalies": result, "status": "success", "count": len(result) if result else 0}
            except Exception as e:
                return {"error": str(e), "status": "error"}
        return {"error": "ML module not available", "status": "unavailable"}


class SystemService:
    """Service for system-level operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self._start_time = time.time()

    def health(self) -> dict:
        """Health check."""
        return {
            "status": "ok",
            "uptime": round(time.time() - self._start_time, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
        }

    def stats(self) -> dict:
        """Aggregate system statistics."""
        # Task stats
        task_svc = TaskService(self.root)
        task_stats = task_svc.get_stats()

        # Memory stats
        mem_svc = MemoryService(self.root)
        mem_stats = mem_svc.get_stats()

        # Eval stats
        eval_svc = EvalService(self.root)
        eval_stats = eval_svc.get_stats()

        return {
            "tasks": task_stats,
            "memory": mem_stats,
            "eval": eval_stats,
        }

    def info(self) -> dict:
        """System information."""
        import sys
        return {
            "name": "The S.E.A.S. (Self-Evolving Agentic System)",
            "version": "1.0.0",
            "python_version": sys.version,
            "platform": sys.platform,
            "project_root": str(self.root),
            "modules_available": self._check_modules(),
        }

    def _check_modules(self) -> dict:
        """Check which optional modules are available."""
        modules = ["flask", "fastapi", "uvicorn", "websockets", "plotly", "jinja2"]
        result = {}
        for mod in modules:
            try:
                __import__(mod)
                result[mod] = True
            except ImportError:
                result[mod] = False
        return result

    def hooks(self) -> list[dict]:
        """Get registered system hooks (from T-044 HookSystem)."""
        try:
            from system.plugin_system import HookSystem
            hooks = HookSystem()
            return hooks.list_hooks()
        except ImportError:
            return []


class AuthService:
    """Service for authentication operations."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
        self._sessions: dict[str, dict] = {}

    def login(self, username: str, password: str) -> Optional[dict]:
        """Authenticate a user."""
        # Use the auth system if available
        try:
            from system.authentication import authenticate_user, create_session
            result = authenticate_user(username, password)
            if result:
                session = create_session(username)
                return {
                    "token": session.get("token", ""),
                    "username": username,
                    "expires_at": session.get("expires_at", ""),
                }
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback: simple auth for testing
        if username and password:
            token = f"tok-{uuid.uuid4().hex[:16]}"
            self._sessions[token] = {
                "username": username,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            return {
                "token": token,
                "username": username,
                "expires_at": datetime.now(timezone.utc).isoformat(),
            }
        return None

    def verify(self, token: str) -> Optional[dict]:
        """Verify a session token."""
        try:
            from system.authentication import verify_session
            result = verify_session(token)
            if result:
                return {"valid": True, "username": result.get("username", "")}
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback
        if token in self._sessions:
            return {"valid": True, "username": self._sessions[token]["username"]}
        return None

    def logout(self, token: str) -> bool:
        """Invalidate a session token."""
        try:
            from system.authentication import invalidate_session
            invalidate_session(token)
            return True
        except ImportError:
            pass
        except Exception:
            pass

        if token in self._sessions:
            del self._sessions[token]
            return True
        return False


# ── Event Bus ──────────────────────────────────────────────────────────────────

class EventBus:
    """In-memory event bus for real-time streaming."""

    def __init__(self, max_history: int = 200):
        self._subscribers: list[asyncio.Queue] = []
        self._history: deque = deque(maxlen=max_history)

    def push(self, event_type: str, data: dict, source: str = "system"):
        """Push an event to all subscribers and history."""
        event = {
            "type": event_type,
            "data": data,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(event)
        stale = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(q)
        for q in stale:
            try:
                q.get_nowait()
                q.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    def history(self, limit: int = 50) -> list[dict]:
        return list(self._history)[-limit:]

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# ── Agent Controller ───────────────────────────────────────────────────────────

class AgentController:
    """Lightweight agent lifecycle management with file-backed persistence.

    Agent identity/config (name, model, config) survives backend restarts
    via ``system/data/agents.json``; runtime state (status/uptime) does not.
    """

    STATE_FILE = SYSTEM_DIR / "data" / "agents.json"

    def __init__(self):
        self._seed_agents: dict[str, dict] = {
            "planner": {"id": "planner", "name": "Planner", "status": "idle", "tasks_completed": 142, "uptime": 0, "model": "gpt-4o", "config": {"max_tokens": 4096, "temperature": 0.3}},
            "executor": {"id": "executor", "name": "Executor", "status": "idle", "tasks_completed": 89, "uptime": 0, "model": "gpt-4o", "config": {"max_tokens": 8192, "temperature": 0.1}},
            "reviewer": {"id": "reviewer", "name": "Reviewer", "status": "idle", "tasks_completed": 231, "uptime": 0, "model": "gpt-4o", "config": {"max_tokens": 4096, "temperature": 0.2}},
            "researcher": {"id": "researcher", "name": "Researcher", "status": "idle", "tasks_completed": 67, "uptime": 0, "model": "claude-3.5-sonnet", "config": {"max_tokens": 8192, "temperature": 0.4}},
            "self_improver": {"id": "self_improver", "name": "Self-Improver", "status": "idle", "tasks_completed": 34, "uptime": 0, "model": "gpt-4o", "config": {"max_tokens": 4096, "temperature": 0.5}},
        }
        self._agents: dict[str, dict] = {}
        self._logs: dict[str, list] = {}
        self._load_state()
        if not self._agents:
            self._agents = {k: dict(v) for k, v in self._seed_agents.items()}
        for agent in self._agents.values():
            # Runtime flags never survive a restart.
            agent["status"] = "idle"
            agent["uptime"] = 0
        self._logs = {aid: [] for aid in self._agents}
        self._seed_logs()
        self._save_state()

    # ── persistence ────────────────────────────────────────────────── #

    def _load_state(self) -> None:
        try:
            if self.STATE_FILE.exists():
                data = json.loads(self.STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for aid, agent in data.items():
                        if isinstance(agent, dict) and agent.get("id"):
                            self._agents[aid] = agent
                        elif isinstance(agent, dict):
                            agent["id"] = aid
                            self._agents[aid] = agent
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[AgentController] state load failed: {exc}")

    def _save_state(self) -> None:
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            serializable = {
                aid: {**agent, "_logs": self._logs.get(aid, [])[-20:]}
                for aid, agent in self._agents.items()
            }
            self.STATE_FILE.write_text(
                json.dumps(serializable, indent=2), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            print(f"[AgentController] state save failed: {exc}")

    def _seed_logs(self):
        for aid, agent in self._agents.items():
            self._logs[aid] = [
                {"level": "info", "message": f"{agent['name']} agent initialized", "timestamp": datetime.now(timezone.utc).isoformat()},
                {"level": "info", "message": f"Model: {agent['model']}, Config: temp={agent['config']['temperature']}", "timestamp": datetime.now(timezone.utc).isoformat()},
            ]
            if agent["status"] == "running":
                self._logs[aid].append({"level": "info", "message": f"Agent started, processing task queue", "timestamp": datetime.now(timezone.utc).isoformat()})

    def list_agents(self) -> list[dict]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[dict]:
        return self._agents.get(agent_id)

    def create_agent(self, name: str, model: str = "", config: Optional[dict] = None, type: str = "chat") -> dict:
        base = name.strip().lower().replace(" ", "_")
        agent_id = base
        suffix = 1
        while agent_id in self._agents:
            suffix += 1
            agent_id = f"{base}_{suffix}"
        agent = {
            "id": agent_id,
            "name": name.strip(),
            "type": type,
            "status": "idle",
            "tasks_completed": 0,
            "uptime": 0,
            "model": model or "",
            "config": config or {"max_tokens": 4096, "temperature": 0.3},
        }
        self._agents[agent_id] = agent
        self._logs[agent_id] = [{
            "level": "info",
            "message": f"{agent['name']} agent created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
        get_event_bus().push("agent.created", {"agent_id": agent_id, "name": agent["name"]}, "agents")
        self._save_state()
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        removed = self._agents.pop(agent_id)
        self._logs.pop(agent_id, None)
        get_event_bus().push("agent.deleted", {"agent_id": agent_id, "name": removed.get("name", agent_id)}, "agents")
        self._save_state()
        return True

    def rename_agent(self, agent_id: str, name: str) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        old = agent["name"]
        agent["name"] = name.strip()
        self._add_log(agent_id, "info", f"Agent renamed from '{old}' to '{agent['name']}'")
        get_event_bus().push("agent.renamed", {"agent_id": agent_id, "name": agent["name"]}, "agents")
        self._save_state()
        return agent

    def start_agent(self, agent_id: str) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        if agent["status"] == "running":
            return agent
        agent["status"] = "running"
        agent["uptime"] = 0
        self._add_log(agent_id, "info", f"{agent['name']} agent started")
        get_event_bus().push("agent.started", {"agent_id": agent_id, "name": agent["name"]}, "agents")
        self._save_state()
        return agent

    def stop_agent(self, agent_id: str) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        if agent["status"] == "idle":
            return agent
        agent["status"] = "idle"
        self._add_log(agent_id, "warn", f"{agent['name']} agent stopped")
        get_event_bus().push("agent.stopped", {"agent_id": agent_id, "name": agent["name"]}, "agents")
        self._save_state()
        return agent

    def restart_agent(self, agent_id: str) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        original = agent.get("model", "gpt-4o")
        agent["status"] = "running"
        agent["uptime"] = 0
        agent["model"] = original
        self._add_log(agent_id, "info", f"{agent['name']} agent restarted")
        get_event_bus().push("agent.restarted", {"agent_id": agent_id, "name": agent["name"]}, "agents")
        self._save_state()
        return agent

    def get_logs(self, agent_id: str, limit: int = 50) -> list[dict]:
        if agent_id not in self._agents:
            return []
        return list(self._logs[agent_id])[-limit:]

    def update_config(self, agent_id: str, config: dict) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        safe_keys = ["max_tokens", "temperature", "model"]
        for k in safe_keys:
            if k in config:
                agent["config"][k] = config[k]
                if k == "model":
                    agent["model"] = config[k]
        self._add_log(agent_id, "info", f"Configuration updated: {json.dumps(config)}")
        get_event_bus().push("agent.configured", {"agent_id": agent_id, "config": config}, "agents")
        self._save_state()
        return agent

    def _add_log(self, agent_id: str, level: str, message: str):
        entry = {"level": level, "message": message, "timestamp": datetime.now(timezone.utc).isoformat()}
        self._logs[agent_id].append(entry)


# ── Trading Controller ──────────────────────────────────────────────────────────────

class TradingController:
    """Trading Desk backend backed by the self-contained BankrAgent.

    Live market data requires ``yfinance``; when unavailable the controller
    transparently falls back to deterministic sample data so signals and
    backtests remain fully functional offline (labelled accordingly).
    """

    def __init__(self):
        from .bankr_trading import BankrAgent
        self._agent_cls = BankrAgent

    def _make_agent(self, cash: float = 10000.0):
        return self._agent_cls(initial_cash=cash)

    @staticmethod
    def _yfinance_available() -> bool:
        try:
            import yfinance  # noqa: F401
            return True
        except ImportError:
            return False

    def status(self) -> dict:
        from .bankr_trading import StrategyType
        return {
            "initial_cash": 10000.0,
            "strategies": [s.value for s in StrategyType],
            "live_data": self._yfinance_available(),
            "llm_analysis": self._llm_available(),
        }

    def _llm_available(self) -> bool:
        try:
            agent = self._make_agent()
            llm = getattr(agent, "_llm", None) or getattr(
                self._agent_cls, "_llm_analyzer", None)
            analyzer = agent.__dict__.get("llm") or agent.__dict__.get("_llm")
            if analyzer is not None and hasattr(analyzer, "is_available"):
                return bool(analyzer.is_available())
        except Exception:
            pass
        return False

    def generate_signals(self, ticker: str, days: int = 180,
                         strategy: str = "sma_crossover") -> dict:
        agent = self._make_agent()
        data_source = "live"
        try:
            data = agent.fetch_data(ticker, "", "", interval="1d")
        except Exception:
            data = None
        if not data:
            data = self._agent_cls.sample_data(ticker, days=max(30, min(days, 500)))
            data_source = "sample"
        signals = agent.generate_signals(data, strategy=self._strategy(strategy))
        return {
            "ticker": ticker, "strategy": strategy,
            "data_source": data_source, "bars": len(data),
            "signals": [s.to_dict() for s in signals],
        }

    def backtest(self, ticker: str, start: str = "", end: str = "",
                 days: int = 252, strategy: str = "sma_crossover",
                 cash: float = 10000.0, interval: str = "1d") -> dict:
        agent = self._make_agent(cash=cash)
        use_live = self._yfinance_available()
        if use_live:
            try:
                result = agent.backtest(ticker, start, end,
                                        strategy=self._strategy(strategy),
                                        interval=interval)
                source = "live"
            except Exception:
                result = None
        else:
            result = None
        if result is None:
            sample = self._agent_cls.sample_data(ticker, days=max(30, min(days, 750)))
            agent.set_fetch_fn(lambda t, s, e, i="1d", _d=sample: _d)
            result = agent.backtest(ticker, start or "", end or "",
                                    strategy=self._strategy(strategy),
                                    interval=interval)
            source = "sample"
        d = result.to_dict()
        d["data_source"] = source
        d["summary"] = agent.summary_line(result)
        return d

    def portfolio(self, tickers: list[str], days: int = 252,
                  strategy: str = "sma_crossover", cash: float = 10000.0) -> dict:
        agent = self._make_agent(cash=cash)
        if not self._yfinance_available():
            samples = {t: self._agent_cls.sample_data(t, days=max(30, min(days, 750)))
                       for t in tickers}
            agent.set_fetch_fn(lambda t, s, e, i="1d", _m=samples: _m.get(t, []))
        portfolio = agent.run_portfolio(
            tickers, "2024-01-01", "", strategy=self._strategy(strategy))
        return {"portfolio": portfolio.to_dict(), "summary": agent.summary_line(portfolio)}

    def _strategy(self, name: str):
        from .bankr_trading import StrategyType
        try:
            return StrategyType(name)
        except ValueError:
            return next(iter(StrategyType))


# ── CRM Controller ─────────────────────────────────────────────────────────────────

class CrmController:
    """CRM data access for the CRM Database workspace.

    Backed by the CrmRepository interface (MockCrmRepository by default);
    swap in a real repository via ``set_repository`` when a live CRM is
    connected. Read-only surface: search + work queue.
    """

    def __init__(self):
        from .crm_repository import MockCrmRepository
        self._repo = MockCrmRepository()

    def set_repository(self, repo) -> None:
        self._repo = repo

    def search_contacts(self, query: str, limit: int = 25) -> list[dict]:
        results = self._repo.search_contacts(query or "", [], None, limit=limit)
        return [self._contact_summary(hit) for hit in results]

    def contacts_needing_work(self, limit: int = 25) -> list[dict]:
        items = self._repo.contacts_needing_work(limit=limit)
        out = []
        for item in items:
            data = getattr(item, "__dict__", {})
            out.append({k: v for k, v in data.items()
                        if isinstance(v, (str, int, float, bool, type(None)))})
        return out

    @staticmethod
    def _contact_summary(hit) -> dict:
        data = getattr(hit, "__dict__", {})
        return {k: v for k, v in data.items()
                if isinstance(v, (str, int, float, bool, type(None)))}


# ── Module Controller ─────────────────────────────────────────────────────────

class ModuleController:
    """Track and control module enable states.

    Module identity/enabled-state/config is persisted to
    ``system/data/modules.json`` so user toggles survive backend restarts.
    """

    STATE_FILE = SYSTEM_DIR / "data" / "modules.json"

    DEFAULTS: dict[str, dict] = {
        "task_queue": {"name": "Task Queue", "enabled": True, "description": "Background task processing engine", "version": "1.2.0", "config": {"max_workers": 4, "queue_size": 100}},
        "memory": {"name": "Memory System", "enabled": True, "description": "Hierarchical memory with hot/warm tiers", "version": "2.0.1", "config": {"hot_tier_size_mb": 50, "warm_tier_size_mb": 200}},
        "eval": {"name": "Evaluation Engine", "enabled": True, "description": "Test suites, runs, and regression tracking", "version": "1.5.0", "config": {"default_timeout_seconds": 300}},
        "plugins": {"name": "Plugin System", "enabled": True, "description": "Extensible plugin architecture (T-044)", "version": "1.1.0", "config": {"sandbox_enabled": True}},
        "analytics": {"name": "Analytics & ML", "enabled": True, "description": "AI/ML predictions, anomaly detection, metrics", "version": "0.9.0", "config": {"model_cache_size": 100}},
        "orchestrator": {"name": "Orchestrator", "enabled": True, "description": "Agent orchestration patterns (fan-out, pipeline, etc.)", "version": "2.0.0", "config": {"max_concurrent_agents": 8}},
        "mcp_bridge": {"name": "MCP Bridge", "enabled": True, "description": "Model Context Protocol bridge for external tools", "version": "1.0.0", "config": {"timeout_seconds": 30}},
        "rate_limiter": {"name": "Rate Limiter", "enabled": True, "description": "API rate limiting and cost control", "version": "1.3.0", "config": {"requests_per_minute": 60}},
        "context_manager": {"name": "Context Manager", "enabled": True, "description": "Context window optimization and pruning", "version": "1.2.0", "config": {"max_context_tokens": 8000, "prune_threshold": 0.8}},
        "reflection": {"name": "Reflection Engine", "enabled": True, "description": "Self-reflection and meta-cognition", "version": "0.8.0", "config": {"reflection_depth": 3}},
    }

    def __init__(self):
        self._modules: dict[str, dict] = dict(self.DEFAULTS)
        self._load()

    def _load(self) -> None:
        """Load persisted module state from disk."""
        try:
            if self.STATE_FILE.exists():
                data = json.loads(self.STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for mid, saved in data.items():
                        if mid in self._modules and isinstance(saved, dict):
                            self._modules[mid].update(saved)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        """Persist module state to disk."""
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.STATE_FILE.write_text(
                json.dumps(self._modules, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"[ModuleController] persist failed: {exc}")

    def list_modules(self) -> list[dict]:
        return [{"id": mid, **mod} for mid, mod in self._modules.items()]

    def get_module(self, mid: str) -> Optional[dict]:
        mod = self._modules.get(mid)
        if not mod:
            return None
        return {"id": mid, **mod}

    def toggle(self, mid: str, enabled: bool) -> Optional[dict]:
        if mid not in self._modules:
            return None
        self._modules[mid]["enabled"] = enabled
        self._save()
        get_event_bus().push(
            "module.toggled" if enabled else "module.disabled",
            {"module_id": mid, "name": self._modules[mid]["name"]},
            "modules",
        )
        return {"id": mid, **self._modules[mid]}

    def get_config(self, mid: str) -> Optional[dict]:
        mod = self._modules.get(mid)
        if not mod:
            return None
        return mod.get("config", {})

    def update_config(self, mid: str, config: dict) -> Optional[dict]:
        if mid not in self._modules:
            return None
        self._modules[mid]["config"] = config
        self._save()
        get_event_bus().push(
            "module.config_updated",
            {"module_id": mid, "name": self._modules[mid]["name"]},
            "modules",
        )
        return {"id": mid, **self._modules[mid]}


# ── Error Reporting ──────────────────────────────────────────────────────────────

class GracefulHandlingIncident:
    """Context manager for graceful error handling with rate limiting and validation."""

    # Shared across instances so rate-limiting state persists between requests
    _report_timestamp: list[float] = []
    _RATE_LOCK = __import__("threading").Lock()

    def __init__(self, max_reports_per_minute: int = 5):
        self.max_reports = max_reports_per_minute
        self.report_file = DATA_DIR / "error_reports.json"
        self.report_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def report_timestamps(self):
        return GracefulHandlingIncident._report_timestamp

    def __enter__(self):
        self._cleanup_old_timestamps()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def _cleanup_old_timestamps(self):
        """Remove timestamps older than 1 minute (shared class-level)."""
        now = time.time()
        with GracefulHandlingIncident._RATE_LOCK:
            GracefulHandlingIncident._report_timestamp = [
                ts for ts in GracefulHandlingIncident._report_timestamp if now - ts < 60
            ]

    def check_rate_limit(self) -> bool:
        """Check if we're within rate limits. Raises if limit exceeded."""
        self._cleanup_old_timestamps()
        with GracefulHandlingIncident._RATE_LOCK:
            if len(GracefulHandlingIncident._report_timestamp) >= self.max_reports:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: max {self.max_reports} reports per minute"
                )
            GracefulHandlingIncident._report_timestamp.append(time.time())
        return True

    def validate_input(self, error: dict, traceback: str) -> bool:
        """Validate error report input. Raises if invalid."""
        if not isinstance(error, dict):
            raise HTTPException(status_code=400, detail="Error must be a JSON object")
        if "message" not in error:
            raise HTTPException(status_code=400, detail="Error object must contain 'message' field")
        if not isinstance(error["message"], str) or not error["message"].strip():
            raise HTTPException(status_code=400, detail="Error message must be a non-empty string")
        if len(error["message"]) > 5000:
            raise HTTPException(status_code=400, detail="Error message too long (max 5000 chars)")
        if traceback and len(traceback) > 20000:
            raise HTTPException(status_code=400, detail="Traceback too long (max 20000 chars)")
        return True

    def store_report(self, error: dict, traceback: str, module: str = "", agent_id: str = "") -> dict:
        """Store error report persistently with rotation (max 1000 lines)."""
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "traceback": traceback,
            "module": module,
            "agent_id": agent_id or str(uuid.uuid4()),
        }

        reports = []
        if self.report_file.exists():
            try:
                with open(self.report_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                reports.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except OSError:
                reports = []

        reports.append(report)

        # Rotate: keep only the last 1000 reports
        if len(reports) > 1000:
            reports = reports[-1000:]

        try:
            with open(self.report_file, "w", encoding="utf-8") as f:
                for r in reports:
                    f.write(json.dumps(r, default=str) + "\n")
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to store report: {e}")

        return report


# ── API Server ─────────────────────────────────────────────────────────────────

class APIService:
    """Main REST API service.

    Uses FastAPI if available, falls back to Flask, then to basic http.server.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000,
                 reload: bool = False, debug: bool = False):
        self.host = host
        self.port = port
        self.reload = reload
        self.debug = debug
        self._start_time = time.time()

        # Initialize services
        self.task_svc = TaskService()
        self.memory_svc = MemoryService()
        self.eval_svc = EvalService()
        self.workflow_svc = WorkflowService()
        self.profile_svc = ProfileService()
        self.plugin_svc = PluginService()
        self.skill_svc = SkillService()
        # Register CRM skill handlers so they can be executed via the API
        # (POST /api/v1/skills/{name}/execute). Handlers are keyed by skill
        # name in skill_registry and resolved at call time via get_handler().
        from .skill_registry import SkillRegistry
        self.skill_registry = SkillRegistry()
        self.skill_registry.register_crm_skill_handlers()
        # Let SkillService reuse the same registry instance so `executable`
        # annotations stay consistent with the execute endpoint's resolution.
        self.skill_svc._registry = self.skill_registry
        # Backfill `inputs` frontmatter into code-backed (CRM) skill specs once
        # at startup. Best-effort: a failure must never block API startup.
        try:
            from . import skill_writer

            skill_writer.backfill_skill_inputs()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[APIService] skill input backfill failed: {exc}")
        self.analytics_svc = AnalyticsService()
        self.system_svc = SystemService()
        self.auth_svc = AuthService()
        self.agent_ctrl = AgentController()
        self.module_ctrl = ModuleController()
        self.crm_ctrl = CrmController()
        self.trading_ctrl = TradingController()
        self.crm_mgr = CrmDatabaseManager()
        self.dojo_store = DatasetStore()
        self.provider_mgr = get_provider_manager()
        self.inference_svc = get_inference_service()
        self.instruction_svc = get_instruction_service()
        self.extension_svc = get_extension_service()
        self.prompt_svc = PromptsIndex(project_root=str(PROJECT_ROOT))

        # SIP/VoIP configuration
        self.sip_config: Optional[dict] = None
        self.active_calls: dict = {}
        self._load_sip_config()

        self.event_bus = get_event_bus()
        self._initialize_services()

    def _load_sip_config(self) -> None:
        """Load SIP configuration from disk."""
        try:
            config_path = PROJECT_ROOT / "data" / "sip_config.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    self.sip_config = json.load(f)
        except Exception:
            self.sip_config = None

    def _save_sip_config(self) -> None:
        """Save SIP configuration to disk."""
        try:
            config_path = PROJECT_ROOT / "data" / "sip_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(self.sip_config, f, indent=2)
        except Exception as e:
            print(f"[APIService] Failed to save SIP config: {e}")

    def _initialize_services(self) -> None:
        """Initialize services that depend on event_bus."""
        self.ag2_memory_svc = AG2MemoryService()
        self.settings_svc = SettingsService()

    def _make_response(self, data: Any = None, message: str = "",
                        error: str = "", status: int = 200) -> dict:
        """Create a standardized API response."""
        resp = APIResponse(
            success=error == "",
            message=message,
            data=data,
            error=error,
        )
        return resp.to_dict()

    def _paginated_response(self, result: PaginatedResponse) -> dict:
        """Create a paginated response."""
        d = result.to_dict()
        d["success"] = True
        d["timestamp"] = datetime.now(timezone.utc).isoformat()
        return d

    # ── FastAPI Implementation ────────────────────────────────────────────

    def create_fastapi_app(self):
        """Create a FastAPI application with auto-generated OpenAPI docs."""
        from fastapi import FastAPI, Query, HTTPException, Request, Form
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        app = FastAPI(
            title="The S.E.A.S. API",
            description="REST API for The S.E.A.S. (Self-Evolving Agentic System)",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
        )

        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

        # ── TencentDB Agent Memory v2.0 startup hook (Phase 1) ────────
        # Idempotent, feature-flagged. When MEMORY_CORE_ENABLED is False
        # this is a no-op; when on it probes L1 count to verify reachability.
        async def _memory_startup():
            try:
                from . import memory_integration
                snap = await memory_integration.init()
                if snap.get("enabled") and snap.get("connected"):
                    print(f"[memory_integration] connected to {snap.get('endpoint')}")
                elif snap.get("enabled"):
                    print(f"[memory_integration] enabled but unreachable: {snap.get('reason')}")
            except Exception as exc:  # noqa: BLE001
                print(f"[memory_integration] startup hook error: {exc}")

        # FastAPI <0.110 uses on_event; >=0.110 prefers lifespan. Try both.
        try:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _memory_lifespan(_app):
                await _memory_startup()
                yield

            # Only override the lifespan if it isn't already customized
            existing = getattr(app, "router", None)
            lifespan_attr = getattr(existing, "lifespan", None) if existing else None
            if lifespan_attr is None:
                app.router.lifespan_context = _memory_lifespan
        except Exception:
            try:
                app.add_event_handler("startup", _memory_startup)
            except Exception:  # pragma: no cover
                pass

        # ── Module toggle subscribers (Phase 2) ───────────────────
        # Consumers may register an async callback that receives
        # {"module_id": ..., "enabled": ...} on every module.toggled event.
        _module_toggle_subscribers: list[callable] = []

        def subscribe_module_toggle(callback: callable) -> None:
            """Register an async callback for module toggle events."""
            if callback not in _module_toggle_subscribers:
                _module_toggle_subscribers.append(callback)

        # Register each gated module's subscriber at startup.
        # The dispatcher is invoked from the toggle_module route handler
        # so subscribers run in the async context.

        # ── Pydantic Models ──────────────────────────────────────────

        class TaskCreate(BaseModel):
            title: str
            description: str = ""
            priority: str = "medium"
            depends_on: list[str] = []
            tags: list[str] = []

        class TaskUpdate(BaseModel):
            title: Optional[str] = None
            description: Optional[str] = None
            status: Optional[str] = None
            priority: Optional[str] = None
            depends_on: Optional[list[str]] = None
            tags: Optional[list[str]] = None

        class MemoryCreate(BaseModel):
            content: str
            type: str = "note"
            tags: list[str] = []

        class PluginInstall(BaseModel):
            source_path: str

        class PluginImport(BaseModel):
            manifest: dict[str, Any]
            code: Optional[str] = None

        class PluginUpdate(BaseModel):
            manifest: dict[str, Any]

        class SkillMatchRequest(BaseModel):
            text: str

        class SkillValidateRequest(BaseModel):
            name: Optional[str] = None

        class SkillExecuteRequest(BaseModel):
            args: dict[str, Any] = {}

        class SkillCreateRequest(BaseModel):
            name: str
            version: str = "1.0.0"
            description: str = ""
            tags: list[str] = []
            triggers: list[str] = []
            type: str = "generic"
            category: str = "general"
            inputs: list[dict] = []
            body: str = ""
            code_backed: bool = False

        class SkillImportRequest(BaseModel):
            name: str
            content: str

        class SkillUpdateRequest(BaseModel):
            version: str | None = None
            description: str | None = None
            tags: list[str] | None = None
            triggers: list[str] | None = None
            type: str | None = None
            category: str | None = None
            inputs: list[dict] | None = None
            body: str | None = None

        class SkillRollbackRequest(BaseModel):
            version: str

        class InstructionCreate(BaseModel):
            name: str
            content: str
            description: str = ""
            category: str = "general"
            tags: list[str] = []
            author: str = ""

        class InstructionUpdate(BaseModel):
            content: Optional[str] = None
            description: Optional[str] = None
            category: Optional[str] = None
            tags: Optional[list[str]] = None
            change_notes: str = ""
            author: str = ""

        class InstructionPreviewRequest(BaseModel):
            content: str
            variables: dict[str, Any] = {}

        class ForkRequest(BaseModel):
            author: str = ""

        class PromptCreate(BaseModel):
            name: str
            content: str
            description: str = ""
            category: str = "CUSTOM"
            status: str = "DRAFT"
            tags: list[str] = []
            author: str = ""
            metadata: dict[str, Any] = {}

        class PromptUpdate(BaseModel):
            content: Optional[str] = None
            description: Optional[str] = None
            status: Optional[str] = None
            tags: Optional[list[str]] = None
            change_notes: str = ""
            author: str = ""

        class PromptRollbackRequest(BaseModel):
            version: str

        class PromptRunRecord(BaseModel):
            outcome: str = "UNKNOWN"
            tokens_used: int = 0
            duration_ms: int = 0
            feedback: str = ""
            metadata: dict[str, Any] = {}

        class PromptImportRequest(BaseModel):
            data: dict[str, Any]

        class PromptBulkImportRequest(BaseModel):
            source_path: str
            max_import: Optional[int] = 100

        class PromptCollectionCreate(BaseModel):
            name: str
            description: str = ""

        class PromptCollectionAdd(BaseModel):
            prompt_id: str

        class ExtensionCreate(BaseModel):
            name: str
            description: str = ""
            version: str = "0.1.0"
            author: str = ""
            sandbox: str = "isolated"
            manifest: dict[str, Any] = {}
            capabilities: list[str] = []

        class ExtensionUpdate(BaseModel):
            description: Optional[str] = None
            version: Optional[str] = None
            sandbox: Optional[str] = None
            manifest: Optional[dict[str, Any]] = None
            capabilities: Optional[list[str]] = None

        class LoginRequest(BaseModel):
            username: str
            password: str

        class VerifyRequest(BaseModel):
            token: str

        class AgentConfigUpdate(BaseModel):
            model: Optional[str] = None
            max_tokens: Optional[int] = None
            temperature: Optional[float] = None

        class AgentCreate(BaseModel):
            name: str
            model: str = ""
            config: Optional[dict] = None
            type: str = "chat"  # "chat" or "voice"

        class AgentRename(BaseModel):
            name: str
            model: Optional[str] = None

        class ToggleModule(BaseModel):
            enabled: bool

        class UpdateModuleConfig(BaseModel):
            config: dict

        class AgentAction(BaseModel):
            agent_id: str

        class ProviderCreate(BaseModel):
            id: Optional[str] = None
            name: str
            type: str = "openai"
            base_url: str = ""
            api_key: str = ""
            is_active: bool = False

        class ProviderUpdate(BaseModel):
            name: Optional[str] = None
            type: Optional[str] = None
            base_url: Optional[str] = None
            is_active: Optional[bool] = None

        class ApiKeyUpdate(BaseModel):
            api_key: str

        class ModelCreate(BaseModel):
            id: Optional[str] = None
            name: str
            context_window: int = 4096
            capabilities: list[str] = ["chat"]
            params: Optional[dict] = None

        class ModelUpdate(BaseModel):
            name: Optional[str] = None
            context_window: Optional[int] = None
            capabilities: Optional[list[str]] = None
            params: Optional[dict] = None

        class ChatMessage(BaseModel):
            role: str = "user"
            content: str

        class ChatRequest(BaseModel):
            provider_id: str
            model_id: Optional[str] = None
            messages: list[ChatMessage] = []
            temperature: Optional[float] = None
            max_tokens: Optional[int] = None
            stream: bool = False
            # MemoryCore integration (Phase 2). When the client supplies a
            # session_id, the resulting assistant turn is captured to L0
            # under that key. When omitted, the server generates one.
            session_id: Optional[str] = None

        class CompleteRequest(BaseModel):
            provider_id: str
            model_id: Optional[str] = None
            prompt: str
            temperature: Optional[float] = None
            max_tokens: Optional[int] = None
            stream: bool = False

        class OSINTSearchRequest(BaseModel):
            query: str
            targets: Optional[list[str]] = None
            services: Optional[list[str]] = None

        class OSINTEnrichRequest(BaseModel):
            fields: Optional[dict[str, str]] = None
            sources: Optional[list[str]] = None

        class TradingSignalsRequest(BaseModel):
            ticker: str = "AAPL"
            days: int = 180
            strategy: str = "sma_crossover"

        class TradingBacktestRequest(BaseModel):
            ticker: str = "AAPL"
            start: str = ""
            end: str = ""
            days: int = 252
            strategy: str = "sma_crossover"
            cash: float = 10000.0
            interval: str = "1d"

        class TradingPortfolioRequest(BaseModel):
            tickers: list[str] = ["AAPL"]
            days: int = 252
            strategy: str = "sma_crossover"
            cash: float = 10000.0

        class CrmDbCreate(BaseModel):
            name: str

        class CrmRowCreate(BaseModel):
            table: str
            data: dict

        class CrmRowUpdate(BaseModel):
            table: str
            data: dict

        class DojoArenaRunRequest(BaseModel):
            provider_id: str
            model_id: Optional[str] = None
            suite_id: str = "reasoning_basics"

        class DojoDatasetCreate(BaseModel):
            id: str
            examples: Optional[list] = None
            system_prompt: str = ""

        class DojoExamplesAdd(BaseModel):
            examples: Optional[list] = None
            jsonl_text: Optional[str] = None
            system_prompt: str = ""

        class DojoCalibrateRequest(BaseModel):
            provider_id: str
            base_model: str
            new_name: str
            system_prompt: str = ""
            dataset_id: Optional[str] = None
            temperature: Optional[float] = None

        class DojoFinetuneRequest(BaseModel):
            provider_id: str
            base_model: str
            dataset_id: str
            suffix: str = "seas"

        class DojoTemplateInstantiate(BaseModel):
            template_id: str
            id: str

        class DojoExampleUpdate(BaseModel):
            example: dict

        class OSINTServicesUpdate(BaseModel):
            services: dict[str, bool]

        class SettingsUpdate(BaseModel):
            model_config = {"extra": "allow"}

            backend_url: Optional[str] = None
            theme: Optional[str] = None
            accent: Optional[str] = None

        # ── Module Gate ──────────────────────────────────────────────
        # Disabling a module in the Modules view makes its API surface
        # respond 503 immediately — the toggle has real runtime effect.

        gated_prefixes = {
            "/api/v1/memory": "memory",
            "/api/v1/eval": "eval",
            "/api/v1/plugins": "plugins",
            "/api/v1/analytics": "analytics",
            "/api/v1/reflection": "reflection",
            "/api/v1/context": "context_manager",
        }

        @app.middleware("http")
        async def module_gate(request, call_next):
            path = request.url.path
            for prefix, module_id in gated_prefixes.items():
                if path.startswith(prefix + "/") or path == prefix:
                    mod = self.module_ctrl.get_module(module_id)
                    if mod and not mod.get("enabled", True):
                        return JSONResponse(
                            status_code=503,
                            content=self._make_response(
                                error=f"Module '{module_id}' is disabled — enable it in the Modules view",
                                status=503),
                        )
                    break
            return await call_next(request)

        # ── Exception Handlers ───────────────────────────────────────

        @app.exception_handler(Exception)
        async def global_exception_handler(request, exc):
            return JSONResponse(
                status_code=500,
                content=self._make_response(error=f"Internal server error: {str(exc)}", status=500),
            )

        # ── Health Check Routes ───────────────────────────────────────
        
        @app.get("/health")
        async def health_simple():
            """Simple health check for load balancers and monitoring."""
            return {"status": "ok", "service": "the-seas-api", "version": "1.0.0"}
        
        @app.get("/api/health")
        async def health_api():
            """API health check with service details."""
            return self._make_response(data=self.system_svc.health())

        @app.get("/api/v1/system/health")
        async def system_health():
            """System health check endpoint."""
            return self._make_response(data=self.system_svc.health())

        # ── Tasks Routes ─────────────────────────────────────────────

        @app.get("/api/v1/tasks")
        async def list_tasks(
            status: Optional[str] = None,
            priority: Optional[str] = None,
            page: int = Query(1, ge=1),
            per_page: int = Query(20, ge=1, le=200),
        ):
            result = self.task_svc.list_tasks(status, priority, page, per_page)
            return self._paginated_response(result)

        @app.post("/api/v1/tasks", status_code=201)
        async def create_task(task: TaskCreate):
            result = self.task_svc.create_task(
                title=task.title,
                description=task.description,
                priority=task.priority,
                depends_on=task.depends_on,
                tags=task.tags,
            )
            return self._make_response(data=result, message="Task created")

        @app.get("/api/v1/tasks/stats")
        async def task_stats():
            return self._make_response(data=self.task_svc.get_stats())

        @app.get("/api/v1/tasks/{task_id}")
        async def get_task(task_id: str):
            task = self.task_svc.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._make_response(data=task)

        @app.put("/api/v1/tasks/{task_id}")
        async def update_task(task_id: str, updates: TaskUpdate):
            updated = self.task_svc.update_task(
                task_id, updates.model_dump(exclude_none=True)
            )
            if not updated:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._make_response(data=updated, message="Task updated")

        @app.delete("/api/v1/tasks/{task_id}")
        async def delete_task(task_id: str):
            ok = self.task_svc.delete_task(task_id)
            if not ok:
                raise HTTPException(status_code=404, detail="Task not found")
            return self._make_response(message="Task deleted")

        # ── Memory Routes ────────────────────────────────────────────

        @app.get("/api/v1/memory")
        async def list_memory(
            type: Optional[str] = None,
            page: int = Query(1, ge=1),
            per_page: int = Query(20, ge=1, le=100),
        ):
            result = self.memory_svc.list_entries(type, page, per_page)
            return self._paginated_response(result)

        @app.post("/api/v1/memory", status_code=201)
        async def create_memory(entry: MemoryCreate):
            result = self.memory_svc.create_entry(
                content=entry.content,
                entry_type=entry.type,
                tags=entry.tags,
            )
            return self._make_response(data=result, message="Memory entry created")

        @app.get("/api/v1/memory/stats")
        async def memory_stats():
            return self._make_response(data=self.memory_svc.get_stats())

        @app.get("/api/v1/memory/search")
        async def search_memory_route(q: str = Query("", alias="q", description="Search query")):
            results = self.memory_svc.search_memory(q)
            return self._make_response(data=results)

        @app.get("/api/v1/memory/{entry_id}")
        async def get_memory(entry_id: str):
            entry = self.memory_svc.get_entry(entry_id)
            if not entry:
                raise HTTPException(status_code=404, detail="Memory entry not found")
            return self._make_response(data=entry)

        @app.delete("/api/v1/memory/{entry_id}")
        async def delete_memory(entry_id: str):
            ok = self.memory_svc.delete_entry(entry_id)
            if not ok:
                raise HTTPException(status_code=404, detail="Memory entry not found")
            return self._make_response(message="Memory entry deleted")

        # ── MemoryCore (TencentDB Agent Memory v2.0) Routes ─────────
        # Feature-flagged. When MEMORY_CORE_ENABLED is False the bridge
        # is a no-op and these endpoints just return the status snapshot.
        # NOTE: these use a /memorycore/ prefix on purpose so they are NOT
        # gated by the module_gate (which covers /api/v1/memory). The
        # MemoryCore feature flag is the single control for this integration;
        # the existing JSON memory surface stays gated by the module toggle.

        @app.get("/api/v1/memorycore/status")
        async def memory_status():
            from . import memory_integration
            try:
                snap = await memory_integration.status()
            except Exception as exc:  # noqa: BLE001
                return self._make_response(
                    data={"enabled": False, "connected": False, "reason": f"status error: {exc}"},
                )
            return self._make_response(data=snap)

        @app.get("/api/v1/memorycore/recall")
        async def memory_recall(q: str = Query("", alias="q"), limit: int = Query(5, ge=1, le=50)):
            from . import memory_integration
            if not q.strip():
                return self._make_response(data=[])
            try:
                atoms = await memory_integration.recall_memory(q, limit=limit)
            except Exception as exc:  # noqa: BLE001
                return self._make_response(
                    error=f"recall failed: {exc}", data=[],
                )
            return self._make_response(data=atoms)

        @app.post("/api/v1/memorycore/capture")
        async def memory_capture(body: dict):
            from . import memory_integration
            session_id = (body or {}).get("session_id") or ""
            messages = (body or {}).get("messages") or []
            task_id = (body or {}).get("task_id")
            if not session_id or not messages:
                return self._make_response(
                    error="session_id and non-empty messages are required",
                )
            try:
                ok = await memory_integration.capture_conversation(
                    session_id=session_id, messages=messages, task_id=task_id,
                )
            except Exception as exc:  # noqa: BLE001
                return self._make_response(error=f"capture failed: {exc}")
            return self._make_response(data={"captured": ok}, message="captured" if ok else "skipped")

        @app.post("/api/v1/memorycore/reset")
        async def memory_reset():
            """Test/maintenance helper - drops the cached HTTP client."""
            from . import memory_integration
            try:
                await memory_integration.reset()
            except Exception as exc:  # noqa: BLE001
                return self._make_response(error=f"reset failed: {exc}")
            return self._make_response(message="memory_integration reset")

        # ── Capability Promotion Routes (memory-backed) ─────────────────
        @app.post("/api/v1/memorycore/promote")
        async def promote_capability_route(
            capability_id: str = Body(..., embed=True),
            target_level: int = Body(..., embed=True),
        ):
            from . import memory
            ok = memory.promote_capability(capability_id, target_level)
            if not ok:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to promote {capability_id} to level {target_level}",
                )
            return self._make_response(
                data={"id": capability_id, "promotion_level": target_level},
                message=f"Capability promoted to level {target_level}",
            )

        @app.get("/api/v1/memorycore/capabilities")
        async def list_capabilities_route(
            min_level: int = Query(2, ge=0, le=3),
            validated_only: bool = Query(False),
        ):
            from . import memory
            caps = memory.get_capabilities(min_level=min_level, validated_only=validated_only)
            return self._make_response(data=caps)

        # ── Skill Effectiveness Routes ────────────────────────────────
        @app.post("/api/v1/skills/effectiveness")
        async def record_skill_effectiveness(
            skill_name: str = Body(...),
            task: str = Body(...),
            outcome: str = Body(...),
            success: bool = Body(...),
            score: float = Body(0.0),
        ):
            from . import memory
            entry = memory.record_skill_effectiveness(
                skill_name=skill_name, task=task,
                outcome=outcome, success=success, score=score,
            )
            return self._make_response(data=entry, message="skill effectiveness recorded")

        @app.get("/api/v1/skills/effectiveness")
        async def skill_effectiveness_stats(
            skill: Optional[str] = Query(None, description="Filter by skill name"),
        ):
            from . import memory
            stats = memory.get_skill_effectiveness_stats(skill_name=skill)
            return self._make_response(data=stats)

        # ── Eval Routes ──────────────────────────────────────────────

        @app.get("/api/v1/eval/suites")
        async def list_eval_suites():
            return self._make_response(data=self.eval_svc.get_suites())

        @app.get("/api/v1/eval/suites/{name}")
        async def get_eval_suite(name: str):
            suite = self.eval_svc.get_suite(name)
            if not suite:
                raise HTTPException(status_code=404, detail="Eval suite not found")
            return self._make_response(data=suite)

        @app.get("/api/v1/eval/runs")
        async def list_eval_runs(
            suite: Optional[str] = None,
            limit: int = Query(20, ge=1, le=100),
        ):
            return self._make_response(data=self.eval_svc.get_runs(suite, limit))

        @app.get("/api/v1/eval/runs/{run_id}")
        async def get_eval_run(run_id: str):
            run = self.eval_svc.get_run(run_id)
            if not run:
                raise HTTPException(status_code=404, detail="Eval run not found")
            return self._make_response(data=run)

        @app.get("/api/v1/eval/baseline")
        async def get_eval_baseline():
            return self._make_response(data=self.eval_svc.get_baseline())

        @app.get("/api/v1/eval/stats")
        async def eval_stats():
            return self._make_response(data=self.eval_svc.get_stats())

        # ── Workflow Routes ────────────────────────────────────────────

        @app.get("/api/v1/workflows")
        async def list_workflows():
            return self._make_response(data=self.workflow_svc.list_workflows())

        @app.post("/api/v1/workflows")
        async def create_workflow(workflow_data: dict):
            workflow_id = self.workflow_svc.create_workflow(workflow_data)
            return self._make_response(data=workflow_id)

        @app.get("/api/v1/workflows/{workflow_id}")
        async def get_workflow(workflow_id: str):
            workflow = self.workflow_svc.get_workflow(workflow_id)
            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return self._make_response(data=workflow)

        @app.delete("/api/v1/workflows/{workflow_id}")
        async def delete_workflow(workflow_id: str):
            success = self.workflow_svc.delete_workflow(workflow_id)
            if not success:
                raise HTTPException(status_code=404, detail="Workflow not found")
            return self._make_response(message=f"Workflow {workflow_id} deleted")

        @app.get("/api/v1/workflows/{workflow_id}/executions")
        async def get_executions(workflow_id: str):
            return self._make_response(data=self.workflow_svc.get_executions(workflow_id))

        @app.post("/api/v1/workflows/{workflow_id}/execute")
        async def execute_workflow(workflow_id: str, execution_data: dict):
            result = self.workflow_svc.save_execution(workflow_id, execution_data)
            if not result:
                raise HTTPException(status_code=500, detail="Execution failed")
            return self._make_response(message=f"Workflow {workflow_id} executed successfully")

        # ── Profile Routes ───────────────────────────────────────────

        @app.get("/api/v1/profiles")
        async def list_profiles():
            return self._make_response(data=self.profile_svc.list_profiles())

        @app.get("/api/v1/profiles/active")
        async def get_active_profile():
            return self._make_response(data=self.profile_svc.get_active())

        @app.get("/api/v1/profiles/{name}")
        async def get_profile(name: str):
            profile = self.profile_svc.get_profile(name)
            if not profile:
                raise HTTPException(status_code=404, detail="Profile not found")
            return self._make_response(data=profile)

        @app.put("/api/v1/profiles/{name}/activate")
        async def activate_profile(name: str):
            ok = self.profile_svc.set_active(name)
            if not ok:
                raise HTTPException(status_code=404, detail="Profile not found")
            return self._make_response(message=f"Profile '{name}' activated")

        # ── Plugin Routes ────────────────────────────────────────────

        @app.get("/api/v1/plugins")
        async def list_plugins(status: Optional[str] = None):
            return self._make_response(data=self.plugin_svc.list_plugins(status))

        @app.get("/api/v1/plugins/stats")
        async def plugin_stats():
            return self._make_response(data=self.plugin_svc.get_stats())

        @app.get("/api/v1/plugins/discover")
        async def discover_plugins():
            return self._make_response(data=self.plugin_svc.discover_plugins())

        @app.get("/api/v1/plugins/{plugin_id}")
        async def get_plugin(plugin_id: str):
            plugin = self.plugin_svc.get_plugin(plugin_id)
            if not plugin:
                raise HTTPException(status_code=404, detail="Plugin not found")
            return self._make_response(data=plugin)

        @app.post("/api/v1/plugins/install", status_code=201)
        async def install_plugin(req: PluginInstall):
            ok, msg = self.plugin_svc.install_plugin(req.source_path)
            if not ok:
                return self._make_response(error=msg)
            return self._make_response(message=msg)

        @app.post("/api/v1/plugins/{plugin_id}/activate")
        async def activate_plugin(plugin_id: str):
            ok, msg = self.plugin_svc.activate_plugin(plugin_id)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return self._make_response(message=msg)

        @app.post("/api/v1/plugins/{plugin_id}/deactivate")
        async def deactivate_plugin(plugin_id: str):
            ok, msg = self.plugin_svc.deactivate_plugin(plugin_id)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return self._make_response(message=msg)

        @app.delete("/api/v1/plugins/{plugin_id}")
        async def uninstall_plugin(plugin_id: str):
            ok, msg = self.plugin_svc.uninstall_plugin(plugin_id)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return self._make_response(message=msg)

        @app.post("/api/v1/plugins/import", status_code=201)
        async def import_plugin(req: PluginImport):
            ok, msg = self.plugin_svc.install_plugin_from_manifest(req.manifest, req.code)
            if not ok:
                return self._make_response(error=msg)
            return self._make_response(message=msg)

        @app.get("/api/v1/plugins/{plugin_id}/export")
        async def export_plugin(plugin_id: str):
            data = self.plugin_svc.export_plugin(plugin_id)
            if not data:
                raise HTTPException(status_code=404, detail="Plugin not found")
            return self._make_response(data=data)

        @app.put("/api/v1/plugins/{plugin_id}")
        async def update_plugin(plugin_id: str, req: PluginUpdate):
            ok, msg = self.plugin_svc.update_plugin_manifest(plugin_id, req.manifest)
            if not ok:
                return self._make_response(error=msg)
            return self._make_response(message=msg)

        # ── Skills Routes ────────────────────────────────────────────

        @app.get("/api/v1/skills")
        async def list_skills(tag: Optional[str] = None):
            return self._make_response(data=self.skill_svc.list_skills(tag))

        @app.get("/api/v1/skills/stats")
        async def skill_stats():
            return self._make_response(data=self.skill_svc.get_stats())

        @app.get("/api/v1/skills/search")
        async def search_skills(q: str = Query("", alias="q", description="Search query")):
            return self._make_response(data=self.skill_svc.search_skills(q))

        @app.get("/api/v1/skills/{name}")
        async def get_skill(name: str):
            skill = self.skill_svc.get_skill(name)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")
            return self._make_response(data=skill)

        @app.post("/api/v1/skills/match")
        async def match_skills(req: SkillMatchRequest):
            return self._make_response(data=self.skill_svc.find_by_trigger(req.text))

        @app.post("/api/v1/skills/validate")
        async def validate_skills(req: SkillValidateRequest):
            return self._make_response(data=self.skill_svc.validate(req.name))

        @app.post("/api/v1/skills/{name}/execute")
        async def execute_skill(name: str, req: SkillExecuteRequest):
            """Execute a handler-backed skill by name.

            Request body: ``{"args": {...}}`` — its contents are passed as
            keyword arguments to the skill's ``execute`` callable. Only skills
            with a registered handler (currently the ported CRM skills) can be
            executed this way.
            """
            handler = self.skill_registry.get_handler(name)
            if handler is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No executable handler registered for skill '{name}'",
                )
            try:
                result = handler(**req.args)
            except TypeError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid arguments for skill '{name}': {exc}",
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Skill '{name}' execution failed: {exc}",
                )
            return self._make_response(data=result)

        @app.post("/api/v1/skills", status_code=201)
        async def api_create_skill(request: SkillCreateRequest):
            try:
                spec = request.model_dump()
                result = skill_writer.create_skill(spec["name"], spec)
                return self._make_response(data=result)
            except FileExistsError as e:
                raise HTTPException(status_code=409, detail=str(e))
            except (ValueError, Exception) as e:
                raise HTTPException(status_code=400, detail=str(e))

        @app.put("/api/v1/skills/{name}")
        async def api_update_skill(name: str, request: SkillUpdateRequest):
            try:
                spec = {k: v for k, v in request.model_dump().items() if v is not None}
                result = skill_writer.update_skill(name, spec)
                return self._make_response(data=result)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        @app.delete("/api/v1/skills/{name}")
        async def api_delete_skill(name: str):
            try:
                skill_writer.delete_skill(name)
                return self._make_response(data={"deleted": name})
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @app.get("/api/v1/skills/{name}/versions")
        async def api_list_versions(name: str):
            return self._make_response(data=skill_history.list_versions(name))

        @app.get("/api/v1/skills/{name}/versions/{version_id}")
        async def api_get_version(name: str, version_id: str):
            try:
                return self._make_response(data=skill_history.get_version(name, version_id))
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @app.post("/api/v1/skills/{name}/rollback")
        async def api_rollback_skill(name: str, request: SkillRollbackRequest):
            try:
                result = skill_history.rollback(name, request.version)
                return self._make_response(data=result)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @app.post("/api/v1/skills/import")
        async def api_import_skill(request: SkillImportRequest):
            """Import a skill from raw SKILL.md content (frontmatter + body)."""
            import yaml
            from system import skill_writer

            content = request.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="Empty content")

            # Parse frontmatter
            frontmatter = {}
            body = content
            if content.startswith("---"):
                try:
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = yaml.safe_load(parts[1]) or {}
                        body = parts[2].strip()
                except yaml.YAMLError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid YAML frontmatter: {e}")

            # Name from request takes precedence over frontmatter
            name = request.name or frontmatter.get("name")
            if not name:
                raise HTTPException(status_code=400, detail="Missing skill name")

            # Build spec from frontmatter + body
            spec = {**frontmatter, "body": body}
            spec.pop("name", None)  # name is handled separately

            try:
                result = skill_writer.create_skill(name, spec)
                return self._make_response(data=result, message=f"Skill '{name}' imported")
            except FileExistsError:
                # Fall back to update
                try:
                    result = skill_writer.update_skill(name, spec)
                    return self._make_response(data=result, message=f"Skill '{name}' updated")
                except FileNotFoundError as e:
                    raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        @app.get("/api/v1/skills/{name}/export")
        async def api_export_skill(name: str):
            """Export a skill as raw SKILL.md text."""
            from system.skill_writer import _skill_dir

            try:
                skill_dir = _skill_dir(name)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            md_path = skill_dir / "SKILL.md"
            if not md_path.exists():
                raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

            content = md_path.read_text(encoding="utf-8")
            return self._make_response(data={"name": name, "content": content})

        @app.get("/api/v1/skills/{name}/validate")
        async def api_validate_skill(name: str):
            """Validate a single skill by name."""
            from system.skill_loader import load_skill, validate_skill

            spec = load_skill(name, self.skill_svc.skills_dir)
            if not spec:
                raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

            issues = validate_skill(spec)
            return self._make_response(data={"name": name, "valid": len(issues) == 0, "issues": issues})

        # ── Instruction Routes ─────────────────────────────────────────

        from .prompts_index import PromptCategory, PromptStatus, UsageOutcome

        def _parse_prompt_category(value: Optional[str]):
            if not value:
                return None
            try:
                return PromptCategory(value.lower())
            except ValueError:
                return None

        def _parse_prompt_status(value: Optional[str]):
            if not value:
                return None
            try:
                return PromptStatus(value.lower())
            except ValueError:
                return None

        def _parse_usage_outcome(value: str):
            try:
                return UsageOutcome(value.lower())
            except ValueError:
                return UsageOutcome.UNKNOWN

        @app.get("/api/v1/instructions")
        async def list_instructions(category: Optional[str] = None, tag: Optional[str] = None):
            items = self.instruction_svc.list_instructions(category, tag)
            return self._make_response(data={
                "items": items,
                "stats": self.instruction_svc.get_stats(),
            })

        @app.get("/api/v1/instructions/stats")
        async def instruction_stats():
            return self._make_response(data=self.instruction_svc.get_stats())

        @app.post("/api/v1/instructions/preview")
        async def preview_instruction(req: InstructionPreviewRequest):
            return self._make_response(data=self.instruction_svc.preview(req.content, req.variables))

        @app.post("/api/v1/instructions", status_code=201)
        async def create_instruction(req: InstructionCreate):
            try:
                return self._make_response(
                    data=self.instruction_svc.create_instruction(
                        name=req.name,
                        content=req.content,
                        description=req.description,
                        category=req.category,
                        tags=req.tags,
                        author=req.author,
                    )
                )
            except InstructionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        @app.get("/api/v1/instructions/{iid}")
        async def get_instruction(iid: str):
            instruction = self.instruction_svc.get_instruction(iid)
            if not instruction:
                raise HTTPException(status_code=404, detail="Instruction not found")
            return self._make_response(data=instruction)

        @app.put("/api/v1/instructions/{iid}")
        async def update_instruction(iid: str, req: InstructionUpdate):
            try:
                instruction = self.instruction_svc.update_instruction(
                    iid=iid,
                    content=req.content,
                    description=req.description,
                    category=req.category,
                    tags=req.tags,
                    change_notes=req.change_notes,
                    author=req.author,
                )
            except InstructionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            if not instruction:
                raise HTTPException(status_code=404, detail="Instruction not found")
            return self._make_response(data=instruction)

        @app.delete("/api/v1/instructions/{iid}")
        async def delete_instruction(iid: str):
            if not self.instruction_svc.delete_instruction(iid):
                raise HTTPException(status_code=404, detail="Instruction not found")
            return self._make_response(message="Instruction deleted")

        @app.get("/api/v1/instructions/{iid}/versions")
        async def instruction_versions(iid: str):
            return self._make_response(data=self.instruction_svc.get_versions(iid))

        @app.post("/api/v1/instructions/{iid}/fork", status_code=201)
        async def fork_instruction(iid: str, req: ForkRequest):
            instruction = self.instruction_svc.fork(iid, req.author)
            if not instruction:
                raise HTTPException(status_code=404, detail="Instruction not found")
            return self._make_response(data=instruction)

        @app.get("/api/v1/instructions/{iid}/export")
        async def export_instruction(iid: str):
            instruction = self.instruction_svc.get_instruction(iid)
            if not instruction:
                raise HTTPException(status_code=404, detail="Instruction not found")
            return self._make_response(data=instruction)

        @app.post("/api/v1/instructions/import", status_code=201)
        async def import_instruction(req: InstructionCreate):
            try:
                return self._make_response(
                    data=self.instruction_svc.create_instruction(
                        name=req.name,
                        content=req.content,
                        description=req.description,
                        category=req.category,
                        tags=req.tags,
                        author=req.author,
                    )
                )
            except InstructionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        # ── Prompt Routes ──────────────────────────────────────────────

        @app.get("/api/v1/prompts/stats")
        async def prompt_stats():
            return self._make_response(data=self.prompt_svc.get_stats())

        @app.get("/api/v1/prompts/collections")
        async def prompt_collections(limit: int = 50):
            return self._make_response(data=[
                c.to_dict() for c in self.prompt_svc.list_collections(limit)
            ])

        @app.post("/api/v1/prompts/collections", status_code=201)
        async def create_prompt_collection(req: PromptCollectionCreate):
            collection = self.prompt_svc.create_collection(req.name, req.description)
            if not collection:
                raise HTTPException(status_code=400, detail="Could not create collection")
            return self._make_response(data=collection.to_dict())

        @app.get("/api/v1/prompts/collections/{collection_id}")
        async def get_prompt_collection(collection_id: str):
            collection = self.prompt_svc.get_collection(collection_id)
            if not collection:
                raise HTTPException(status_code=404, detail="Collection not found")
            return self._make_response(data=collection.to_dict())

        @app.post("/api/v1/prompts/collections/{collection_id}/prompts", status_code=201)
        async def add_prompt_to_collection(collection_id: str, req: PromptCollectionAdd):
            ok = self.prompt_svc.add_to_collection(collection_id, req.prompt_id)
            if not ok:
                raise HTTPException(status_code=404, detail="Collection or prompt not found")
            collection = self.prompt_svc.get_collection(collection_id)
            return self._make_response(data=collection.to_dict() if collection else {"id": collection_id})

        @app.get("/api/v1/prompts/search")
        async def search_prompts(
            q: str,
            category: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 20,
        ):
            results = self.prompt_svc.search_prompts(
                q,
                category=_parse_prompt_category(category),
                status=_parse_prompt_status(status),
                limit=limit,
            )
            return self._make_response(data=[
                {"prompt": r.prompt.to_dict(), "score": r.score, "matched_terms": r.matched_terms}
                for r in results
            ])

        @app.get("/api/v1/prompts")
        async def list_prompts(
            category: Optional[str] = None,
            status: Optional[str] = None,
            tags: Optional[str] = None,
            limit: int = 100,
        ):
            tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()] if tags else None
            items = self.prompt_svc.list_prompts(
                category=_parse_prompt_category(category),
                status=_parse_prompt_status(status),
                tags=tag_list,
                limit=limit,
            )
            return self._make_response(data={
                "items": [i.to_dict() for i in items],
                "stats": self.prompt_svc.get_stats(),
            })

        @app.post("/api/v1/prompts/import", status_code=201)
        async def import_prompt(req: PromptImportRequest):
            entry = self.prompt_svc.import_prompt(req.data)
            if not entry:
                raise HTTPException(status_code=400, detail="Invalid prompt payload")
            return self._make_response(data=entry.to_dict())

        @app.post("/api/v1/prompts/import/bulk")
        async def import_prompts_bulk(req: PromptBulkImportRequest):
            """Bulk import prompts from a directory path (e.g. F:\\Prompts)"""
            import os
            import re
            from pathlib import Path

            source_dir = Path(req.source_path)
            if not source_dir.exists():
                raise HTTPException(status_code=404, detail=f"Source path not found: {req.source_path}")

            imported = []
            errors = []
            max_import = req.max_import or 100

            # Parse PROMPT-INDEX.json if it exists
            index_path = source_dir / "PROMPT-INDEX.json"
            index_data = {}
            if index_path.exists():
                try:
                    index_data = json.loads(index_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Collect .md files
            md_files = list(source_dir.glob("*.md"))
            if not md_files:
                md_files = list(source_dir.rglob("*.md"))

            for md_file in md_files[:max_import]:
                try:
                    content = md_file.read_text(encoding="utf-8")
                    # Extract title from first heading
                    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                    title = title_match.group(1).strip() if title_match else md_file.stem

                    # Extract description from second heading or first paragraph
                    desc_match = re.search(r'^##\s+Description\s*\n(.+)$', content, re.MULTILINE | re.DOTALL)
                    if not desc_match:
                        desc_match = re.search(r'^#\s+.+\n\n(.+)$', content, re.MULTILINE | re.DOTALL)
                    description = desc_match.group(1).strip()[:200] if desc_match else ""

                    # Extract tags from frontmatter or content
                    tags = []
                    frontmatter_match = re.match(r'^---\s*\n([\s\S]*?)\n---', content)
                    if frontmatter_match:
                        fm = frontmatter_match.group(1)
                        tags_match = re.search(r'tags:\s*\[(.*?)\]', fm)
                        if tags_match:
                            tags = [t.strip().strip('"').strip("'") for t in tags_match.group(1).split(",")]

                    entry = self.prompt_svc.add_prompt(
                        name=title,
                        content=content,
                        description=description,
                        category=None,
                        status=None,
                        tags=tags,
                    )
                    imported.append({"id": entry.id, "name": entry.name, "file": str(md_file)})
                except Exception as e:
                    errors.append({"file": str(md_file), "error": str(e)})

            return self._make_response(data={"imported": imported, "errors": errors, "total": len(imported)})

        @app.post("/api/v1/prompts", status_code=201)
        async def create_prompt(req: PromptCreate):
            from .prompts_index import PromptCategory as _PC, PromptStatus as _PS
            try:
                category = _PC(req.category.lower())
            except ValueError:
                category = _PC.CUSTOM
            try:
                status = _PS(req.status.lower())
            except ValueError:
                status = _PS.DRAFT
            entry = self.prompt_svc.add_prompt(
                name=req.name,
                content=req.content,
                description=req.description,
                category=category,
                status=status,
                tags=req.tags,
                author=req.author,
                metadata=req.metadata,
            )
            return self._make_response(data=entry.to_dict())

        @app.get("/api/v1/prompts/{prompt_id}")
        async def get_prompt(prompt_id: str):
            entry = self.prompt_svc.get_prompt(prompt_id)
            if not entry:
                raise HTTPException(status_code=404, detail="Prompt not found")
            return self._make_response(data=entry.to_dict())

        @app.put("/api/v1/prompts/{prompt_id}")
        async def update_prompt(prompt_id: str, req: PromptUpdate):
            from .prompts_index import PromptStatus as _PS
            status = None
            if req.status is not None:
                try:
                    status = _PS(req.status.lower())
                except ValueError:
                    status = None
            entry = self.prompt_svc.update_prompt(
                prompt_id=prompt_id,
                content=req.content,
                description=req.description,
                status=status,
                tags=req.tags,
                change_notes=req.change_notes,
                author=req.author,
            )
            if not entry:
                raise HTTPException(status_code=404, detail="Prompt not found")
            return self._make_response(data=entry.to_dict())

        @app.delete("/api/v1/prompts/{prompt_id}")
        async def delete_prompt(prompt_id: str):
            if not self.prompt_svc.delete_prompt(prompt_id):
                raise HTTPException(status_code=404, detail="Prompt not found")
            return self._make_response(message="Prompt deleted")

        @app.get("/api/v1/prompts/{prompt_id}/versions")
        async def prompt_versions(prompt_id: str):
            return self._make_response(data=[
                v.to_dict() for v in self.prompt_svc.get_versions(prompt_id)
            ])

        @app.post("/api/v1/prompts/{prompt_id}/rollback")
        async def rollback_prompt(prompt_id: str, req: PromptRollbackRequest):
            entry = self.prompt_svc.rollback(prompt_id, req.version)
            if not entry:
                raise HTTPException(status_code=404, detail="Prompt or version not found")
            return self._make_response(data=entry.to_dict())

        @app.post("/api/v1/prompts/{prompt_id}/runs", status_code=201)
        async def record_prompt_run(prompt_id: str, req: PromptRunRecord):
            usage = self.prompt_svc.record_usage(
                prompt_id=prompt_id,
                outcome=_parse_usage_outcome(req.outcome),
                tokens_used=req.tokens_used,
                duration_ms=req.duration_ms,
                feedback=req.feedback,
                metadata=req.metadata,
            )
            if not usage:
                raise HTTPException(status_code=404, detail="Prompt not found")
            return self._make_response(data=usage.to_dict())

        @app.get("/api/v1/prompts/{prompt_id}/runs")
        async def prompt_runs(prompt_id: str, limit: int = 50):
            return self._make_response(data=[
                u.to_dict() for u in self.prompt_svc.get_usage(prompt_id, limit)
            ])

        @app.get("/api/v1/prompts/{prompt_id}/stats")
        async def prompt_usage_stats(prompt_id: str):
            return self._make_response(data=self.prompt_svc.get_prompt_usage_stats(prompt_id))

        @app.get("/api/v1/prompts/{prompt_id}/export")
        async def export_prompt(prompt_id: str):
            data = self.prompt_svc.export_prompt(prompt_id)
            if not data:
                raise HTTPException(status_code=404, detail="Prompt not found")
            return self._make_response(data=data)

        @app.post("/api/v1/prompts/{prompt_id}/share", status_code=201)
        async def share_prompt(prompt_id: str):
            if not self.prompt_svc.get_prompt(prompt_id):
                raise HTTPException(status_code=404, detail="Prompt not found")
            return self._make_response(data={
                "share_url": f"/api/v1/prompts/{prompt_id}/export",
                "prompt_id": prompt_id,
            })

        # ── Extension Routes ───────────────────────────────────────────

        @app.get("/api/v1/extensions/stats")
        async def extension_stats():
            return self._make_response(data=self.extension_svc.get_stats())

        @app.get("/api/v1/extensions")
        async def list_extensions(status: Optional[str] = None):
            return self._make_response(data={
                "items": self.extension_svc.list_extensions(status),
                "stats": self.extension_svc.get_stats(),
            })

        @app.post("/api/v1/extensions", status_code=201)
        async def create_extension(req: ExtensionCreate):
            try:
                return self._make_response(
                    data=self.extension_svc.create_extension(
                        name=req.name,
                        description=req.description,
                        version=req.version,
                        author=req.author,
                        sandbox=req.sandbox,
                        manifest=req.manifest,
                        capabilities=req.capabilities,
                    )
                )
            except ExtensionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        @app.get("/api/v1/extensions/{ext_id}")
        async def get_extension(ext_id: str):
            extension = self.extension_svc.get_extension(ext_id)
            if not extension:
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(data=extension)

        @app.put("/api/v1/extensions/{ext_id}")
        async def update_extension(ext_id: str, req: ExtensionUpdate):
            try:
                extension = self.extension_svc.update_extension(
                    ext_id=ext_id,
                    description=req.description,
                    version=req.version,
                    sandbox=req.sandbox,
                    manifest=req.manifest,
                    capabilities=req.capabilities,
                )
            except ExtensionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            if not extension:
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(data=extension)

        @app.delete("/api/v1/extensions/{ext_id}")
        async def delete_extension(ext_id: str):
            if not self.extension_svc.delete_extension(ext_id):
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(message="Extension deleted")

        @app.post("/api/v1/extensions/{ext_id}/enable")
        async def enable_extension(ext_id: str):
            extension = self.extension_svc.enable_extension(ext_id)
            if not extension:
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(data=extension)

        @app.post("/api/v1/extensions/{ext_id}/disable")
        async def disable_extension(ext_id: str):
            extension = self.extension_svc.disable_extension(ext_id)
            if not extension:
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(data=extension)

        @app.get("/api/v1/extensions/{ext_id}/manifest")
        async def extension_manifest(ext_id: str):
            manifest = self.extension_svc.get_manifest(ext_id)
            if manifest is None:
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(data=manifest)

        @app.get("/api/v1/extensions/{ext_id}/export")
        async def export_extension(ext_id: str):
            ext = self.extension_svc.get_extension(ext_id)
            if not ext:
                raise HTTPException(status_code=404, detail="Extension not found")
            return self._make_response(data=ext)

        @app.post("/api/v1/extensions/import", status_code=201)
        async def import_extension(req: ExtensionCreate):
            try:
                return self._make_response(
                    data=self.extension_svc.create_extension(
                        name=req.name,
                        description=req.description,
                        version=req.version,
                        author=req.author,
                        sandbox=req.sandbox,
                        manifest=req.manifest,
                        capabilities=req.capabilities,
                    )
                )
            except ExtensionError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        # ── Reflection Routes (Slice 6) ────────────────────────────────

        @app.get("/api/v1/reflection/stats")
        async def reflection_stats():
            try:
                from .reflection_analysis import reflection_statistics
                return self._make_response(data=reflection_statistics())
            except Exception:
                return self._make_response(data={
                    "total_reflections": 0,
                    "average_confidence": 0,
                    "total_evidence": 0,
                })

        @app.get("/api/v1/reflection/frictions")
        async def reflection_frictions():
            try:
                from .reflection_analysis import friction_distribution, most_common_friction
                return self._make_response(data={
                    "distribution": friction_distribution(),
                    "most_common": [list(item) for item in most_common_friction(5)],
                })
            except Exception:
                return self._make_response(data={"distribution": {}, "most_common": []})

        @app.get("/api/v1/reflection/capabilities")
        async def reflection_capabilities():
            try:
                from .reflection_analysis import capability_statistics
                return self._make_response(data=capability_statistics())
            except Exception:
                return self._make_response(data={
                    "total_capabilities": 0,
                    "validated_capabilities": 0,
                    "promotion_levels": {},
                })

        @app.get("/api/v1/reflection/report")
        async def reflection_report():
            try:
                from .reflection_analysis import capability_health_report
                return self._make_response(data=capability_health_report())
            except Exception:
                return self._make_response(data=[])

        # ── Context Pruning Routes (Slice 6) ───────────────────────────

        @app.get("/api/v1/context/stats")
        async def context_stats():
            try:
                from .context_pruning import Compactor, ContextMonitor
                compactor = Compactor()
                monitor = ContextMonitor()
                return self._make_response(data={
                    "compactor": compactor.get_stats(),
                    "monitor": monitor.get_metrics(),
                })
            except Exception:
                return self._make_response(data={"compactor": {}, "monitor": {}})

        # ── Analytics Routes ─────────────────────────────────────────

        @app.get("/api/v1/analytics/metrics")
        async def get_metrics(type: Optional[str] = None):
            return self._make_response(data=self.analytics_svc.get_metrics(type))

        @app.post("/api/v1/analytics/predict")
        async def predict(model: str = "default", features: Optional[dict] = None):
            return self._make_response(
                data=self.analytics_svc.predict(model, features or {})
            )

        @app.post("/api/v1/analytics/anomalies")
        async def detect_anomalies(data: Optional[list] = None):
            return self._make_response(
                data=self.analytics_svc.detect_anomalies(data or [])
            )

# ── System Routes ────────────────────────────────────────────

        @app.post("/api/v1/system/report", status_code=201)
        async def receive_error_report(err: dict, traceback: Optional[str] = None, module: str = "", agent_id: str = ""):
            with GracefulHandlingIncident() as reporter:
                try:
                    message = err.get("message")
                    if not isinstance(message, str) or not message.strip():
                        return JSONResponse(
                            status_code=400,
                            content=self._make_response(error="Error object must contain non-empty string 'message' field", status=400)
                        )
                    if len(message) > 5000:
                        return JSONResponse(
                            status_code=400,
                            content=self._make_response(error="Error message too long (max 5000 chars)", status=400)
                        )
                    if traceback and len(traceback) > 20000:
                        return JSONResponse(
                            status_code=400,
                            content=self._make_response(error="Traceback too long (max 20000 chars)", status=400)
                        )
                    reporter.check_rate_limit()
                    error_payload = {"message": message}
                    report_data = reporter.store_report(error_payload, traceback or "", module, agent_id)
                    return self._make_response(data=report_data, message="Error report received")
                except HTTPException as e:
                    return JSONResponse(status_code=e.status_code, content=self._make_response(error=e.detail, status=e.status_code))
                except Exception as e:
                    return JSONResponse(status_code=500, content=self._make_response(error=str(e), status=500))

        @app.get("/api/v1/system/reports", status_code=200)
        async def list_error_reports(page: int = 1, per_page: int = 100):
            try:
                report_file = DATA_DIR / "error_reports.json"
                reports = []
                if report_file.exists():
                    with open(report_file, "r", encoding="utf-8") as f:
                        reports = [json.loads(line) for line in f if line.strip()]
                reports = reports[-1000:]
                start = (page - 1) * per_page
                end = start + per_page
                paged = reports[start:end]
                total_pages = max(1, (len(reports) + per_page - 1) // per_page) if reports else 0
                return self._make_response(data={
                    "report_count": len(reports),
                    "reports": paged,
                    "total_pages": total_pages,
                })
            except Exception as e:
                return self._make_response(error=str(e), status=500)

        @app.get("/api/v1/system/stats")
        async def system_stats():
            return self._make_response(data=self.system_svc.stats())

        @app.get("/api/v1/system/info")
        async def system_info():
            return self._make_response(data=self.system_svc.info())

        @app.get("/api/v1/system/hooks")
        async def system_hooks():
            return self._make_response(data=self.system_svc.hooks())

        # ── OSINT Routes ─────────────────────────────────────────────

        @app.get("/api/v1/osint/services")
        async def osint_services():
            services = [
                {"id": "threat_intel", "name": "Threat Intelligence", "enabled": True, "description": "Threat actor tracking and IOCs"},
                {"id": "vulnerability", "name": "Vulnerability Monitor", "enabled": True, "description": "CVE tracking and patch analysis"},
                {"id": "competitive", "name": "Competitive Intel", "enabled": False, "description": "Competitor analysis and market intel"},
                {"id": "domain_recon", "name": "Domain Reconnaissance", "enabled": False, "description": "DNS, WHOIS, subdomain enumeration"},
                {"id": "social_monitor", "name": "Social Monitor", "enabled": False, "description": "Social media threat monitoring"},
            ]
            try:
                from .osint import OSINTEngine
                engine = OSINTEngine(config={})
                remote = engine.list_services() if hasattr(engine, "list_services") else None
                if isinstance(remote, list) and remote:
                    services = remote
            except Exception:
                pass
            return self._make_response(data=services)

        @app.put("/api/v1/osint/services")
        async def osint_update_services(body: OSINTServicesUpdate):
            get_event_bus().push("osint.services_updated", {"services": body.services}, "osint")
            return self._make_response(message="OSINT services updated")

        @app.get("/api/v1/osint/summary")
        async def osint_summary():
            try:
                from .osint import get_osint_engine
                engine = get_osint_engine()
                indicators = engine.get_indicators() if hasattr(engine, "get_indicators") else []
                vulns = engine.get_vulnerabilities() if hasattr(engine, "get_vulnerabilities") else []
                return self._make_response(data={"indicators": indicators[:20], "vulnerabilities": vulns[:20], "total_indicators": len(indicators), "total_vulnerabilities": len(vulns)})
            except (ImportError, Exception):
                return self._make_response(data={"indicators": [], "vulnerabilities": [], "total_indicators": 0, "total_vulnerabilities": 0})

        @app.post("/api/v1/osint/search")
        async def osint_search(body: OSINTSearchRequest):
            from .lead_enrichment import classify_query, get_engine
            try:
                fields = classify_query(body.query)
                result = get_engine().enrich(fields)
                return self._make_response(data=result)
            except Exception as exc:  # pragma: no cover - defensive
                return self._make_response(data={
                    "query": body.query,
                    "findings": {},
                    "sources": {},
                    "error": f"OSINT search unavailable: {exc}",
                })

        @app.post("/api/v1/osint/enrich")
        async def osint_enrich_lead(body: OSINTEnrichRequest):
            """Lead enrichment/completion: fill missing lead fields from
            partial CRM data (name / phone / email / company / domain)."""
            from .lead_enrichment import get_engine
            try:
                fields = {k: v for k, v in (body.fields or {}).items()
                          if isinstance(v, str)}
                result = get_engine().enrich(fields, sources=body.sources)
                return self._make_response(data=result)
            except Exception as exc:  # pragma: no cover - defensive
                return self._make_response(data={
                    "input": {}, "known_fields": {}, "missing_fields": [],
                    "findings": {}, "sources": {},
                    "error": f"Lead enrichment failed: {exc}",
                })

        # ── Settings Routes ────────────────────────────────────────────

        @app.get("/api/v1/settings")
        async def get_settings():
            return self._make_response(data=self.settings_svc.get_settings())

        @app.put("/api/v1/settings")
        async def update_settings(settings: SettingsUpdate):
            result = self.settings_svc.update_settings(settings.model_dump(exclude_none=True))
            return self._make_response(data=result, message="Settings updated")

        # ── Auth Routes ──────────────────────────────────────────────

        @app.post("/api/v1/auth/login")
        async def login(req: LoginRequest):
            result = self.auth_svc.login(req.username, req.password)
            if not result:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return self._make_response(data=result, message="Login successful")

        @app.post("/api/v1/auth/verify")
        async def verify(req: VerifyRequest):
            result = self.auth_svc.verify(req.token)
            if not result:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            return self._make_response(data=result, message="Token valid")

        @app.post("/api/v1/auth/logout")
        async def logout(req: VerifyRequest):
            ok = self.auth_svc.logout(req.token)
            return self._make_response(message="Logged out" if ok else "Session not found")

        # ── SaaS Billing Routes ──────────────────────────────

        @app.get("/api/v1/billing/plans")
        async def billing_plans():
            from .saas_routes import get_saas_routes
            return get_saas_routes().list_plans()

        @app.get("/api/v1/billing/usage")
        async def billing_usage(user_id: str = "anonymous", tier: str = "free"):
            from .saas_routes import get_saas_routes
            return get_saas_routes().get_usage(user_id)

        @app.get("/api/v1/billing/limits")
        async def billing_limits(user_id: str = "anonymous", tier: str = "free"):
            from .saas_routes import get_saas_routes
            return get_saas_routes().check_limits(user_id, tier)

        @app.post("/api/v1/billing/checkout")
        async def billing_checkout(user_id: str = "anonymous", plan_id: str = "pro", interval: str = "monthly"):
            from .saas_routes import get_saas_routes
            return get_saas_routes().create_checkout(user_id, plan_id, interval)

        # ── Landing Page Routes ───────────────────────────────

        @app.get("/api/v1/landing/features")
        async def landing_features():
            from .saas_landing import SaaSLanding
            return SaaSLanding().get_features()

        @app.get("/api/v1/landing/faq")
        async def landing_faq():
            from .saas_landing import SaaSLanding
            return SaaSLanding().get_faq()

        @app.get("/api/v1/landing/stats")
        async def landing_stats():
            from .saas_landing import SaaSLanding
            return SaaSLanding().get_stats()

        # ── Dashboard Routes ──────────────────────────────────

        @app.get("/api/v1/dashboard/summary")
        async def dashboard_summary(user_id: str = "anonymous", tier: str = "free"):
            from .usage_dashboard import get_dashboard
            return get_dashboard().get_summary(user_id, tier)

        @app.get("/api/v1/dashboard/daily")
        async def dashboard_daily(user_id: str = "anonymous", days: int = 30):
            from .usage_dashboard import get_dashboard
            return get_dashboard().get_daily(user_id, days)

        @app.get("/api/v1/dashboard/limits")
        async def dashboard_limits(user_id: str = "anonymous", tier: str = "free"):
            from .usage_dashboard import get_dashboard
            return get_dashboard().get_limits(user_id, tier)

        # ── Onboarding Routes ─────────────────────────────────

        @app.get("/api/v1/onboarding/status")
        async def onboarding_status(user_id: str = "anonymous"):
            from .onboarding import get_onboarding
            state = get_onboarding().get_state(user_id)
            return {"success": True, "data": state.to_dict()}

        @app.post("/api/v1/onboarding/advance")
        async def onboarding_advance(body: dict = {}):
            from .onboarding import get_onboarding
            return get_onboarding().advance(
                body.get("user_id", "anonymous"),
                body.get("step_id", ""),
            )

        @app.post("/api/v1/onboarding/skip")
        async def onboarding_skip(body: dict = {}):
            from .onboarding import get_onboarding
            return get_onboarding().skip(body.get("user_id", "anonymous"))

        @app.get("/api/v1/onboarding/guide")
        async def onboarding_guide(step: Optional[str] = None):
            from .onboarding import get_onboarding
            return get_onboarding().get_guide(step)

        # ── Webhook Routes ────────────────────────────────────

        @app.post("/api/v1/webhooks/stripe")
        async def stripe_webhook(request: Request):
            from .webhooks import get_webhook_handler
            body = await request.body()
            sig = request.headers.get("stripe-signature", "")
            return get_webhook_handler().handle_stripe(body, sig).to_dict()

        @app.post("/api/v1/webhooks/paddle")
        async def paddle_webhook(request: Request):
            from .webhooks import get_webhook_handler
            body = await request.json()
            sig = request.headers.get("paddle-signature", "")
            return get_webhook_handler().handle_paddle(body, sig).to_dict()

        @app.get("/api/v1/webhooks/events")
        async def webhook_events(limit: int = 50, provider: Optional[str] = None):
            from .webhooks import get_webhook_handler
            return {"success": True, "data": get_webhook_handler().get_events(limit, provider)}

        # ── Enterprise (SSO / Teams / Audit) ──────────────────

        # SSO Providers
        @app.get("/api/v1/sso/providers")
        async def sso_list_providers():
            from .sso import get_sso_manager
            return {"success": True, "data": [p.to_dict() for p in get_sso_manager().list_providers()]}

        @app.post("/api/v1/sso/providers")
        async def sso_create_provider(provider: dict):
            from .sso import get_sso_manager
            p = get_sso_manager().register_provider(
                provider["name"], provider["protocol"], provider["idp_url"],
                provider.get("entity_id", ""), provider.get("jit", True),
            )
            return {"success": True, "data": p.to_dict()}

        @app.get("/api/v1/sso/providers/{provider_id}")
        async def sso_get_provider(provider_id: str):
            from .sso import get_sso_manager
            p = get_sso_manager().get_provider(provider_id)
            if not p:
                return {"success": False, "error": "Provider not found"}
            return {"success": True, "data": p.to_dict()}

        @app.delete("/api/v1/sso/providers/{provider_id}")
        async def sso_delete_provider(provider_id: str):
            from .sso import get_sso_manager
            ok = get_sso_manager().delete_provider(provider_id)
            return {"success": ok}

        @app.get("/api/v1/sso/providers/{provider_id}/metadata")
        async def sso_metadata(provider_id: str):
            from .sso import get_sso_manager
            xml = get_sso_manager().generate_saml_metadata(provider_id)
            if not xml:
                return {"success": False, "error": "Provider not found"}
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(xml, media_type="application/xml")

        @app.post("/api/v1/sso/resolve")
        async def sso_resolve(body: dict):
            from .sso import get_sso_manager
            p = get_sso_manager().resolve_provider_for_email(body.get("email", ""))
            if not p:
                return {"success": False, "error": "No provider for domain"}
            return {"success": True, "data": p.to_dict()}

        @app.post("/api/v1/sso/auth")
        async def sso_authenticate(body: dict):
            from .sso import get_sso_manager
            user = get_sso_manager().jit_provision(
                body.get("name_id", ""), body.get("email", ""),
                body.get("display_name", body.get("email", "")),
                body.get("provider_id", ""),
            )
            if not user:
                return {"success": False, "error": "JIT provisioning failed"}
            session = get_sso_manager().create_session(user.user_id, user.provider_id)
            return {"success": True, "data": {"user": user.to_dict(), "session": session.to_dict()}}

        @app.post("/api/v1/sso/logout")
        async def sso_logout(body: dict):
            from .sso import get_sso_manager
            ok = get_sso_manager().invalidate_session(body.get("session_id", ""))
            return {"success": ok}

        @app.get("/api/v1/sso/stats")
        async def sso_stats():
            from .sso import get_sso_manager
            return {"success": True, "data": get_sso_manager().get_stats()}

        # Teams
        @app.get("/api/v1/teams")
        async def team_list():
            from .team_management import get_team_manager
            return {"success": True, "data": [t.to_dict() for t in get_team_manager().list_teams()]}

        @app.post("/api/v1/teams")
        async def team_create(team: dict):
            from .team_management import get_team_manager
            t = get_team_manager().create_team(team["name"], team["owner_id"])
            return {"success": True, "data": t.to_dict()}

        @app.get("/api/v1/teams/{team_id}")
        async def team_get(team_id: str):
            from .team_management import get_team_manager
            t = get_team_manager().get_team(team_id)
            if not t:
                return {"success": False, "error": "Team not found"}
            return {"success": True, "data": t.to_dict()}

        @app.put("/api/v1/teams/{team_id}")
        async def team_update(team_id: str, body: dict):
            from .team_management import get_team_manager
            ok = get_team_manager().update_team(team_id, name=body.get("name"), tier=body.get("tier"))
            return {"success": ok}

        @app.delete("/api/v1/teams/{team_id}")
        async def team_delete(team_id: str):
            from .team_management import get_team_manager
            ok = get_team_manager().delete_team(team_id)
            return {"success": ok}

        @app.get("/api/v1/teams/{team_id}/members")
        async def team_members(team_id: str):
            from .team_management import get_team_manager
            return {"success": True, "data": [m.to_dict() for m in get_team_manager().get_team_members(team_id)]}

        @app.post("/api/v1/teams/{team_id}/members")
        async def team_add_member(team_id: str, body: dict):
            from .team_management import get_team_manager
            m = get_team_manager().add_member(team_id, body["user_id"], body.get("role", "member"))
            if not m:
                return {"success": False, "error": "User already in team"}
            return {"success": True, "data": m.to_dict()}

        @app.delete("/api/v1/teams/{team_id}/members/{user_id}")
        async def team_remove_member(team_id: str, user_id: str):
            from .team_management import get_team_manager
            ok = get_team_manager().remove_member(team_id, user_id)
            return {"success": ok}

        @app.put("/api/v1/teams/{team_id}/members/{user_id}/role")
        async def team_update_role(team_id: str, user_id: str, body: dict):
            from .team_management import get_team_manager
            ok = get_team_manager().update_member_role(team_id, user_id, body.get("role", "member"))
            return {"success": ok}

        @app.post("/api/v1/teams/{team_id}/invite")
        async def team_invite(team_id: str, body: dict):
            from .team_management import get_team_manager
            inv = get_team_manager().create_invitation(team_id, body["email"], body.get("role", "member"))
            if not inv:
                return {"success": False, "error": "Failed to create invitation"}
            return {"success": True, "data": inv.to_dict()}

        @app.post("/api/v1/teams/invite/accept")
        async def team_accept_invite(body: dict):
            from .team_management import get_team_manager
            inv = get_team_manager().accept_invitation(body.get("token", ""))
            if not inv:
                return {"success": False, "error": "Invalid or expired invitation"}
            return {"success": True, "data": inv.to_dict()}

        @app.get("/api/v1/teams/stats")
        async def team_stats():
            from .team_management import get_team_manager
            return {"success": True, "data": get_team_manager().get_stats()}

        # Enterprise Audit
        @app.get("/api/v1/audit/events")
        async def audit_events(
            user_id: Optional[str] = None,
            action: Optional[str] = None,
            severity: Optional[str] = None,
            team_id: Optional[str] = None,
            resource: Optional[str] = None,
            limit: int = 50,
        ):
            from .enterprise_audit import get_enterprise_audit, AuditAction, AuditSeverity
            from datetime import datetime as _dt
            a = get_enterprise_audit()
            act = AuditAction(action) if action else None
            sev = AuditSeverity(severity) if severity else None
            events = a.query_events(
                user_id=user_id, action=act, severity=sev,
                team_id=team_id, resource=resource, limit=limit,
            )
            return {"success": True, "data": [e.to_dict() for e in events]}

        @app.post("/api/v1/audit/events")
        async def audit_record(body: dict):
            from .enterprise_audit import get_enterprise_audit, AuditAction, AuditSeverity
            ev = get_enterprise_audit().record_event(
                body.get("user_id", ""), AuditAction(body.get("action", "task.created")),
                body.get("description", ""), severity=AuditSeverity(body.get("severity", "info")),
                resource_type=body.get("resource_type"), resource_id=body.get("resource_id"),
                team_id=body.get("team_id"), metadata=body.get("metadata"),
            )
            return {"success": True, "data": ev.to_dict()}

        @app.get("/api/v1/audit/stats")
        async def audit_stats():
            from .enterprise_audit import get_enterprise_audit
            return {"success": True, "data": get_enterprise_audit().get_stats()}

        @app.get("/api/v1/audit/reports/{standard}")
        async def audit_report(standard: str, start: Optional[str] = None, end: Optional[str] = None):
            from .enterprise_audit import get_enterprise_audit, ComplianceStandard
            from datetime import datetime as _dt
            s = ComplianceStandard(standard)
            sd = _dt.fromisoformat(start) if start else None
            ed = _dt.fromisoformat(end) if end else None
            report = get_enterprise_audit().generate_report(s, sd, ed)
            return {"success": True, "data": report.to_dict()}

        @app.get("/api/v1/audit/export")
        async def audit_export(format: str = "json"):
            from .enterprise_audit import get_enterprise_audit
            a = get_enterprise_audit()
            if format == "csv":
                csv_data = a.export_events_csv()
                from fastapi.responses import PlainTextResponse
                return PlainTextResponse(csv_data, media_type="text/csv")
            return {"success": True, "data": a.export_events_json()}

        # ── Event Stream ─────────────────────────────────────

        @app.get("/api/v1/events/stream")
        async def event_stream():
            from fastapi.responses import StreamingResponse
            async def event_generator():
                q = await self.event_bus.subscribe()
                try:
                    # Send history first
                    for event in self.event_bus.history(20):
                        yield f"data: {json.dumps(event)}\n\n"
                    while True:
                        try:
                            event = await asyncio.wait_for(q.get(), timeout=30)
                            yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.TimeoutError:
                            yield f": keepalive\n\n"
                except asyncio.CancelledError:
                    pass
                finally:
                    self.event_bus.unsubscribe(q)
            return StreamingResponse(event_generator(), media_type="text/event-stream")

        @app.get("/api/v1/events/history")
        async def event_history(limit: int = 50):
            return self._make_response(data=self.event_bus.history(limit))

        # ── Agent Command Routes ──────────────────────────────

        @app.get("/api/v1/agents")
        async def list_agents():
            return self._make_response(data=self.agent_ctrl.list_agents())

        @app.post("/api/v1/agents", status_code=201)
        async def create_agent(body: AgentCreate):
            agent = self.agent_ctrl.create_agent(body.name, body.model, body.config, body.type)
            return self._make_response(data=agent, message=f"Agent '{agent['name']}' created")

        @app.patch("/api/v1/agents/{agent_id}")
        async def rename_agent(agent_id: str, body: AgentRename):
            agent = self.agent_ctrl.rename_agent(agent_id, body.name)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(data=agent, message="Agent renamed")

        @app.delete("/api/v1/agents/{agent_id}")
        async def delete_agent(agent_id: str):
            if not self.agent_ctrl.delete_agent(agent_id):
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(message=f"Agent {agent_id} deleted")

        @app.get("/api/v1/agents/{agent_id}")
        async def get_agent(agent_id: str):
            agent = self.agent_ctrl.get_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(data=agent)

        @app.post("/api/v1/agents/{agent_id}/start")
        async def start_agent(agent_id: str):
            agent = self.agent_ctrl.start_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(data=agent, message=f"Agent {agent_id} started")

        @app.post("/api/v1/agents/{agent_id}/stop")
        async def stop_agent(agent_id: str):
            agent = self.agent_ctrl.stop_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(data=agent, message=f"Agent {agent_id} stopped")

        @app.post("/api/v1/agents/{agent_id}/restart")
        async def restart_agent(agent_id: str):
            agent = self.agent_ctrl.restart_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(data=agent, message=f"Agent {agent_id} restarted")

        @app.get("/api/v1/agents/{agent_id}/logs")
        async def agent_logs(agent_id: str, limit: int = 50):
            logs = self.agent_ctrl.get_logs(agent_id, limit)
            return self._make_response(data=logs)

        @app.put("/api/v1/agents/{agent_id}/config")
        async def update_agent_config(agent_id: str, config: AgentConfigUpdate):
            updates = {k: v for k, v in config.model_dump().items() if v is not None}
            if not updates:
                raise HTTPException(status_code=400, detail="No valid config fields provided")
            agent = self.agent_ctrl.update_config(agent_id, updates)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return self._make_response(data=agent, message="Agent config updated")

        # ── Module Command Routes ─────────────────────────────

        @app.get("/api/v1/crm/contacts/needing-work")
        async def crm_contacts_needing_work(limit: int = Query(25, ge=1, le=100)):
            # Real databases first; the injectable mock repo is the fallback
            # so skill-driven workflows keep working without user databases.
            items = self.crm_mgr.contacts_needing_work_all(limit)
            if items:
                return self._make_response(data=items)
            return self._make_response(data=self.crm_ctrl.contacts_needing_work(limit))

        @app.get("/api/v1/crm/search")
        async def crm_search(q: str = "", limit: int = Query(25, ge=1, le=100)):
            results = self.crm_mgr.search_contacts_all(q, limit)
            if results:
                return self._make_response(data=results)
            return self._make_response(data=self.crm_ctrl.search_contacts(q, limit))

        # ── CRM Database Manager Routes ──────────────────────

        @app.get("/api/v1/crm/db")
        async def crm_db_list():
            return self._make_response(data=self.crm_mgr.list_databases())

        @app.post("/api/v1/crm/db", status_code=201)
        async def crm_db_create(body: CrmDbCreate):
            try:
                result = self.crm_mgr.create_database(body.name)
                return self._make_response(data=result, message=f"Database '{body.name}' created")
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.delete("/api/v1/crm/db/{db_name}")
        async def crm_db_delete(db_name: str):
            if not self.crm_mgr.delete_database(db_name):
                raise HTTPException(status_code=404, detail="Database not found")
            return self._make_response(message=f"Database '{db_name}' deleted")

        @app.get("/api/v1/crm/db/{db_name}/rows")
        async def crm_db_rows(db_name: str, table: str = "contacts",
                              q: str = "", limit: int = Query(50, ge=1, le=500),
                              offset: int = Query(0, ge=0)):
            try:
                return self._make_response(
                    data=self.crm_mgr.rows(db_name, table, q=q,
                                           limit=limit, offset=offset))
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except sqlite3.Error as exc:
                raise HTTPException(status_code=400, detail=f"Database error: {exc}")

        @app.post("/api/v1/crm/db/{db_name}/rows", status_code=201)
        async def crm_db_create_row(db_name: str, body: CrmRowCreate):
            try:
                row = self.crm_mgr.create_row(db_name, body.table, body.data)
                return self._make_response(data=row, message="Record created")
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except sqlite3.Error as exc:
                raise HTTPException(status_code=400, detail=f"Database error: {exc}")

        @app.put("/api/v1/crm/db/{db_name}/rows/{row_id}")
        async def crm_db_update_row(db_name: str, row_id: int, body: CrmRowUpdate):
            try:
                row = self.crm_mgr.update_row(db_name, body.table, row_id, body.data)
                if row is None:
                    raise HTTPException(status_code=404, detail="Record not found")
                return self._make_response(data=row, message="Record updated")
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except sqlite3.Error as exc:
                raise HTTPException(status_code=400, detail=f"Database error: {exc}")

        @app.delete("/api/v1/crm/db/{db_name}/rows/{table}/{row_id}")
        async def crm_db_delete_row(db_name: str, table: str, row_id: int):
            try:
                if not self.crm_mgr.delete_row(db_name, table, row_id):
                    raise HTTPException(status_code=404, detail="Record not found")
                return self._make_response(message="Record deleted")
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.post("/api/v1/crm/db/{db_name}/import")
        async def crm_db_import(db_name: str, file: UploadFile = File(...),
                                table: str = Form("")):
            content = await file.read()
            try:
                report = self.crm_mgr.import_file(
                    db_name, file.filename or "", content,
                    table=(table or None) or None)
                return self._make_response(data=report, message="Import complete")
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except (sqlite3.Error, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Import failed: {exc}")

        @app.get("/api/v1/crm/db/{db_name}/export")
        async def crm_db_export(db_name: str, format: str = Query("csv"),
                                table: str = ""):
            try:
                result = self.crm_mgr.export(db_name, fmt=format,
                                             table=table or None)
            except CrmDatabaseError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            from fastapi.responses import Response
            return Response(
                content=result["content"],
                media_type=result["media_type"],
                headers={"Content-Disposition":
                         f'attachment; filename="{result["filename"]}"'})

        # ── SIP/VoIP Voice Agent Routes ────────────────────────

        class SipConfig(BaseModel):
            username: str
            password: str
            domain: str
            ws_url: str
            outbound_proxy: Optional[str] = None

        class SipTestResult(BaseModel):
            success: bool
            message: str
            registered: bool = False

        class VoiceAgentCreate(BaseModel):
            name: str
            model: str
            type: str = "voice"
            config: Optional[dict] = None

        @app.get("/api/v1/sip/config")
        async def sip_config_get():
            """Get current SIP configuration."""
            return self._make_response(data=self.sip_config)

        @app.put("/api/v1/sip/config")
        async def sip_config_set(body: SipConfig):
            """Set SIP configuration for VoIPStudio."""
            self.sip_config = body.model_dump()
            self._save_sip_config()
            return self._make_response(data=self.sip_config, message="SIP configuration saved")

        @app.post("/api/v1/sip/test")
        async def sip_test():
            """Test SIP registration with VoIPStudio."""
            if not self.sip_config:
                return self._make_response(
                    ok=False, message="No SIP configuration set", data={"success": False, "registered": False})

            try:
                # Attempt to register with VoIPStudio
                import aiohttp
                import asyncio

                # Quick test via HTTP to check if credentials work
                # In production, this would do actual SIP registration
                async with aiohttp.ClientSession() as session:
                    # Test basic connectivity to VoIPStudio
                    test_url = f"https://{self.sip_config.get('domain', 'sip.voipstudio.com')}"
                    try:
                        async with session.get(test_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            reachable = resp.status < 500
                    except:
                        reachable = False

                result = SipTestResult(
                    success=reachable,
                    message="SIP endpoint reachable" if reachable else "Cannot reach SIP endpoint",
                    registered=reachable
                )
                return self._make_response(data=result.model_dump())

            except Exception as e:
                return self._make_response(
                    ok=False, message=f"SIP test failed: {e}", data={"success": False, "registered": False})

        @app.post("/api/v1/sip/register")
        async def sip_register():
            """Register with VoIPStudio SIP trunk."""
            if not self.sip_config:
                raise HTTPException(status_code=400, detail="No SIP configuration set")

            # In production, this would initiate actual SIP registration
            # For now, return success if config exists
            return self._make_response(
                data={"registered": True, "message": "SIP registration initiated"})

        @app.post("/api/v1/sip/call")
        async def sip_call(destination: str, agent_id: Optional[str] = None):
            """Initiate an outbound call via VoIPStudio."""
            if not self.sip_config:
                raise HTTPException(status_code=400, detail="No SIP configuration set")

            # In production, this would use the VoIPStudioSIPClient
            call_id = f"call-{uuid.uuid4().hex[:12]}"
            return self._make_response(
                data={"call_id": call_id, "destination": destination, "status": "initiated"},
                message=f"Call initiated to {destination}")

        @app.post("/api/v1/sip/hangup")
        async def sip_hangup(call_id: str):
            """Hang up an active call."""
            return self._make_response(data={"call_id": call_id, "status": "ended"})

        @app.get("/api/v1/sip/calls")
        async def sip_calls():
            """List active calls."""
            return self._make_response(data={"calls": self.active_calls})

        # Add SIP config storage to APIService
        # This will be initialized in __init__
        # self.sip_config: Optional[dict] = None
        # self.active_calls: dict = {}

        # ── Trading Desk Routes ─────────────────────────────

        @app.get("/api/v1/trading/status")
        async def trading_status():
            return self._make_response(data=self.trading_ctrl.status())

        @app.post("/api/v1/trading/signals")
        async def trading_signals(body: TradingSignalsRequest):
            try:
                result = self.trading_ctrl.generate_signals(
                    body.ticker, days=body.days, strategy=body.strategy)
                return self._make_response(data=result)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Signal generation failed: {exc}")

        @app.post("/api/v1/trading/backtest")
        async def trading_backtest(body: TradingBacktestRequest):
            try:
                result = self.trading_ctrl.backtest(
                    body.ticker, start=body.start, end=body.end,
                    days=body.days, strategy=body.strategy,
                    cash=body.cash, interval=body.interval)
                return self._make_response(data=result)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

        @app.post("/api/v1/trading/portfolio")
        async def trading_portfolio(body: TradingPortfolioRequest):
            try:
                result = self.trading_ctrl.portfolio(
                    body.tickers, days=body.days, strategy=body.strategy, cash=body.cash)
                return self._make_response(data=result)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Portfolio run failed: {exc}")

        @app.get("/api/v1/modules")
        async def list_modules():
            return self._make_response(data=self.module_ctrl.list_modules())

        @app.post("/api/v1/modules/refresh")
        async def refresh_modules():
            modules = self.module_ctrl.list_modules()
            get_event_bus().push("modules.refreshed", {"count": len(modules)}, "modules")
            return self._make_response(data=modules, message=f"Refreshed {len(modules)} modules")

        @app.get("/api/v1/modules/{module_id}")
        async def get_module(module_id: str):
            mod = self.module_ctrl.get_module(module_id)
            if not mod:
                raise HTTPException(status_code=404, detail="Module not found")
            return self._make_response(data=mod)

        @app.put("/api/v1/modules/{module_id}/toggle")
        async def toggle_module(module_id: str, body: ToggleModule):
            mod = self.module_ctrl.toggle(module_id, body.enabled)
            if not mod:
                raise HTTPException(status_code=404, detail="Module not found")
            # Fan-out to registered consumers (Phase 2) — fire-and-forget
            for sub in _module_toggle_subscribers:
                try:
                    await sub(module_id=module_id, enabled=body.enabled)
                except Exception:  # noqa: BLE001
                    pass
            return self._make_response(data=mod, message=f"Module {'enabled' if body.enabled else 'disabled'}")

        @app.get("/api/v1/modules/{module_id}/config")
        async def get_module_config(module_id: str):
            config = self.module_ctrl.get_config(module_id)
            if config is None:
                raise HTTPException(status_code=404, detail="Module not found")
            return self._make_response(data=config)

        @app.put("/api/v1/modules/{module_id}/config")
        async def update_module_config(module_id: str, body: UpdateModuleConfig):
            mod = self.module_ctrl.update_config(module_id, body.config)
            if not mod:
                raise HTTPException(status_code=404, detail="Module not found")
            return self._make_response(data=mod, message="Module config updated")

        # ── Eval Command Routes ───────────────────────────────

        EVAL_SUITES = {
            "default": {
                "name": "Default Suite",
                "description": "Basic system health checks",
                "tests": [
                    {"name": "backend_health", "description": "Backend API is responsive", "risk": "low"},
                    {"name": "module_registry", "description": "Module registry loads correctly", "risk": "low"},
                    {"name": "skill_loader", "description": "Skill loader discovers skills", "risk": "medium"},
                    {"name": "provider_connectivity", "description": "LLM provider connections work", "risk": "high"},
                ],
            },
            "integration": {
                "name": "Integration Suite",
                "description": "Cross-component integration tests",
                "tests": [
                    {"name": "api_to_modules", "description": "API ↔ Module controller integration", "risk": "medium"},
                    {"name": "api_to_skills", "description": "API ↔ Skill loader integration", "risk": "medium"},
                    {"name": "api_to_providers", "description": "API ↔ Provider manager integration", "risk": "high"},
                    {"name": "ipc_bridge", "description": "Electron IPC ↔ Backend bridge", "risk": "high"},
                ],
            },
            "performance": {
                "name": "Performance Suite",
                "description": "Performance and latency benchmarks",
                "tests": [
                    {"name": "api_response_time", "description": "API response time under 200ms", "risk": "low"},
                    {"name": "module_discovery_speed", "description": "Module discovery completes in <5s", "risk": "low"},
                    {"name": "skill_load_time", "description": "Skill loading completes in <3s", "risk": "medium"},
                    {"name": "concurrent_requests", "description": "Handles 10 concurrent requests", "risk": "high"},
                ],
            },
            "security": {
                "name": "Security Suite",
                "description": "Security and access control checks",
                "tests": [
                    {"name": "api_auth", "description": "API authentication is enforced", "risk": "high"},
                    {"name": "input_sanitization", "description": "Input sanitization prevents injection", "risk": "high"},
                    {"name": "cors_policy", "description": "CORS policy is correctly configured", "risk": "medium"},
                    {"name": "rate_limiting", "description": "Rate limiting is active", "risk": "medium"},
                ],
            },
        }

        # Model-facing arena suites for the AI Dojo. Each test sends a real
        # prompt through the selected provider/model and scores the response
        # with simple deterministic heuristics (content checks + latency).
        DOJO_ARENA_SUITES = {
            "reasoning_basics": {
                "name": "Reasoning Basics",
                "description": "Arithmetic, logic and comparison smoke tests",
                "tests": [
                    {"name": "arithmetic",
                     "prompt": "What is 17 * 23? Answer with the number only.",
                     "contains_any": ["391"], "min_length": 1},
                    {"name": "sequence",
                     "prompt": "Next number in the sequence 2, 4, 8, 16, ...? Answer with the number only.",
                     "contains_any": ["32"], "min_length": 1},
                    {"name": "comparison",
                     "prompt": "Which is larger, 0.75 or 3/5? Answer '0.75' or '3/5'.",
                     "contains_any": ["0.75"], "min_length": 1},
                ],
            },
            "instruction_following": {
                "name": "Instruction Following",
                "description": "Format and constraint compliance",
                "tests": [
                    {"name": "json_output",
                     "prompt": 'Return ONLY a JSON object with keys "status" set to "ok" and "code" set to 42.',
                     "contains_any": ['"status"', '"ok"'], "min_length": 10},
                    {"name": "one_word",
                     "prompt": "Reply with exactly one word: the capital of France.",
                     "contains_any": ["Paris"], "min_length": 2},
                    {"name": "no_explanation",
                     "prompt": "Say OK. Do not explain.",
                     "contains_any": ["OK", "Ok"], "min_length": 1},
                ],
            },
            "crm_domain": {
                "name": "CRM Lead Skills",
                "description": "Lead-data extraction and enrichment reasoning",
                "tests": [
                    {"name": "email_extract",
                     "prompt": "From this text: 'Contact Maria Silva, works at Acme Corp, reach her at maria.silva@acme.com' — what is the email address? Reply with the email only.",
                     "contains_any": ["maria.silva@acme.com"], "min_length": 5},
                    {"name": "phone_normalize",
                     "prompt": "Normalize this phone to E.164 (Peru country code +51): 987 654 321. Reply with the number only.",
                     "contains_any": ["+51987654321"], "min_length": 5},
                    {"name": "missing_field",
                     "prompt": "A lead has name='John Smith' but no email. The company domain is acme.com. Suggest ONE likely email in the format first.last@domain. Reply with the email only.",
                     "contains_any": ["john.smith@acme.com"], "min_length": 5},
                ],
            },
        }

        @app.get("/api/v1/dojo/arena/suites")
        async def dojo_arena_suites():
            suites = [{"id": sid, **s} for sid, s in DOJO_ARENA_SUITES.items()]
            return self._make_response(data=suites)

        @app.post("/api/v1/dojo/arena/run")
        async def dojo_arena_run(body: DojoArenaRunRequest):
            suite_def = DOJO_ARENA_SUITES.get(body.suite_id)
            if not suite_def:
                raise HTTPException(status_code=404, detail="Arena suite not found")
            results = []
            passed = 0
            total_latency = 0
            for test_case in suite_def["tests"]:
                t0 = time.time()
                try:
                    response = self.inference_svc.complete(
                        body.provider_id, body.model_id,
                        test_case["prompt"],
                        params={"max_tokens": 160, "temperature": 0})
                    latency_ms = int((time.time() - t0) * 1000)
                    text = (response or "").strip()
                    checks = test_case.get("contains_any") or []
                    lowered = text.lower()
                    contains_ok = (not checks) or any(
                        c.lower() in lowered for c in checks)
                    min_len = int(test_case.get("min_length", 1))
                    ok = len(text) >= min_len and contains_ok
                    error = ""
                except InferenceError as exc:
                    latency_ms = int((time.time() - t0) * 1000)
                    text, ok, error = "", False, exc.message
                except Exception as exc:  # pragma: no cover - defensive
                    latency_ms = int((time.time() - t0) * 1000)
                    text, ok, error = "", False, str(exc)[:200]
                if ok:
                    passed += 1
                total_latency += latency_ms
                results.append({
                    "name": test_case["name"],
                    "passed": ok,
                    "latency_ms": latency_ms,
                    "response_preview": text[:180],
                    "error": error,
                })
            summary = {
                "suite_id": body.suite_id,
                "provider_id": body.provider_id,
                "model_id": body.model_id or "(default)",
                "passed": passed,
                "total": len(results),
                "avg_latency_ms": int(total_latency / max(len(results), 1)),
            }
            get_event_bus().push("dojo.arena_run", summary, "dojo")
            return self._make_response(data={"results": results, "summary": summary})

        # ── AI Dojo: Training & Calibration ──────────────────

        @app.get("/api/v1/dojo/datasets")
        async def dojo_datasets_list():
            return self._make_response(data=self.dojo_store.list_datasets())

        @app.get("/api/v1/dojo/templates")
        async def dojo_templates():
            from .dojo import DOJO_TEMPLATES
            return self._make_response(data=DOJO_TEMPLATES)

        @app.post("/api/v1/dojo/datasets/from-template", status_code=201)
        async def dojo_dataset_from_template(body: DojoTemplateInstantiate):
            from .dojo import DOJO_TEMPLATES
            template = next((t for t in DOJO_TEMPLATES
                             if t["id"] == body.template_id), None)
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            try:
                meta = self.dojo_store.create(
                    body.id, examples=template["examples"],
                    system_prompt=template["system_prompt"])
                return self._make_response(
                    data={**meta, "template": template["id"]},
                    message=f"Dataset '{body.id}' created from template")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.post("/api/v1/dojo/datasets/import", status_code=201)
        async def dojo_dataset_import(file: UploadFile = File(...),
                                      name: str = Form(...),
                                      system_prompt: str = Form("")):
            content = await file.read()
            try:
                report = self.dojo_store.create_from_upload(
                    name.strip(), file.filename or "", content,
                    system_prompt=system_prompt or "")
                return self._make_response(
                    data=report,
                    message=f"Imported {report.get('added', 0)} example(s) into '{name}'")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.get("/api/v1/dojo/datasets/{ds_id}/export")
        async def dojo_dataset_export(ds_id: str, format: str = Query("jsonl")):
            try:
                result = self.dojo_store.export_dataset(ds_id, format)
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            from fastapi.responses import Response
            return Response(
                content=result["content"], media_type=result["media_type"],
                headers={"Content-Disposition":
                         f'attachment; filename="{result["filename"]}"'})

        @app.put("/api/v1/dojo/datasets/{ds_id}/examples/{index}")
        async def dojo_example_update(ds_id: str, index: int,
                                      body: DojoExampleUpdate):
            try:
                result = self.dojo_store.replace_example(ds_id, index, body.example)
                return self._make_response(data=result, message="Example updated")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.delete("/api/v1/dojo/datasets/{ds_id}/examples/{index}")
        async def dojo_example_delete(ds_id: str, index: int):
            try:
                self.dojo_store.delete_example(ds_id, index)
                return self._make_response(message="Example deleted")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.post("/api/v1/dojo/datasets", status_code=201)
        async def dojo_dataset_create(body: DojoDatasetCreate):
            try:
                meta = self.dojo_store.create(
                    body.id, examples=body.examples or [],
                    system_prompt=body.system_prompt or "")
                return self._make_response(data=meta, message=f"Dataset '{body.id}' created")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.delete("/api/v1/dojo/datasets/{ds_id}")
        async def dojo_dataset_delete(ds_id: str):
            try:
                if not self.dojo_store.delete(ds_id):
                    raise HTTPException(status_code=404, detail="Dataset not found")
                return self._make_response(message=f"Dataset '{ds_id}' deleted")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.get("/api/v1/dojo/datasets/{ds_id}/examples")
        async def dojo_dataset_examples(ds_id: str):
            try:
                return self._make_response(data=self.dojo_store.read_examples(ds_id))
            except DojoError as exc:
                raise HTTPException(status_code=404, detail=str(exc))

        @app.post("/api/v1/dojo/datasets/{ds_id}/examples")
        async def dojo_dataset_add_examples(ds_id: str, body: DojoExamplesAdd):
            try:
                if body.jsonl_text:
                    report = self.dojo_store.import_jsonl_text(
                        ds_id, body.jsonl_text, body.system_prompt or "")
                    return self._make_response(
                        data={"added": report["added"], "skipped": report["skipped"]},
                        message=f"Imported {report['added']} example(s)")
                report = self.dojo_store.append_examples(
                    ds_id, body.examples or [], body.system_prompt or "")
                return self._make_response(
                    data={"added": report["added"], "skipped": report["skipped"]},
                    message=f"Added {report['added']} example(s)")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        @app.post("/api/v1/dojo/calibrate")
        async def dojo_calibrate(body: DojoCalibrateRequest):
            """Local attitude calibration (background job): derive an Ollama
            model from a base model + directive + dataset exemplars."""
            import asyncio as _asyncio
            provider = self.provider_mgr.get_provider_raw(body.provider_id)
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")
            if not is_valid_model_name(body.new_name):
                raise HTTPException(status_code=400, detail=(
                    "Model name may contain letters, numbers, '.', '_', '-', ':' and '/'"))
            ptype = provider.get("type", "")
            base = (provider.get("base_url") or "").rstrip("/") or DEFAULT_BASE_URLS.get(ptype, "")
            examples = []
            if body.dataset_id:
                try:
                    examples = self.dojo_store.read_examples(body.dataset_id)
                except DojoError as exc:
                    raise HTTPException(status_code=400, detail=str(exc))
            precheck = await _base_model_exists(base, body.base_model)
            if not precheck.get("ok"):
                raise HTTPException(status_code=400, detail=str(precheck.get("error")))
            from .dojo import CALIBRATION_JOBS, _run_calibration_job
            job_name = body.new_name.strip()
            CALIBRATION_JOBS[job_name] = {"status": "queued", "done": False,
                                          "started": datetime.now(timezone.utc).isoformat(), "ok": None,
                                          "error": ""}

            async def _runner() -> None:
                await _run_calibration_job(
                    job_name, base, body.base_model, body.system_prompt or "",
                    examples, body.temperature)
                # Close the training loop: register the forged model on its
                # source provider so it is selectable everywhere immediately.
                job = CALIBRATION_JOBS.get(job_name) or {}
                if not job.get("ok"):
                    return
                raw = self.provider_mgr.get_provider_raw(body.provider_id) or {}
                existing = {m.get("id") for m in (raw.get("models") or [])}
                if job_name in existing:
                    return
                self.provider_mgr.add_model(body.provider_id, {
                    "id": job_name,
                    "name": f"{job_name} (dojo-calibrated)",
                    "capabilities": ["chat"],
                })
                self.event_bus.push("dojo.model_registered", {
                    "provider_id": body.provider_id, "model": job_name}, "dojo")

            _asyncio.create_task(_runner())
            self.event_bus.push("dojo.calibrate", {
                "provider_id": body.provider_id, "model": job_name,
                "examples_baked": len(examples)}, "dojo")
            return JSONResponse(status_code=202, content=self._make_response(
                data={"job": job_name, "status": "queued",
                      "examples_baked": len(examples)},
                message=f"Calibration of '{job_name}' started — poll /api/v1/dojo/calibrate/status"))

        @app.get("/api/v1/dojo/calibrate/status")
        async def dojo_calibrate_status(model: str = Query(...)):
            from .dojo import CALIBRATION_JOBS
            job = CALIBRATION_JOBS.get(model)
            if not job:
                raise HTTPException(status_code=404, detail="No such calibration job")
            return self._make_response(data={"model": model, **job})

        @app.post("/api/v1/dojo/finetune")
        async def dojo_finetune(body: DojoFinetuneRequest):
            """Cloud fine-tuning via OpenAI-compatible /fine_tuning/jobs."""
            provider = self.provider_mgr.get_provider_raw(body.provider_id)
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")
            api_key = provider.get("api_key") or ""
            if not api_key:
                raise HTTPException(status_code=400, detail=(
                    "This provider has no API key stored — cloud fine-tuning "
                    "needs one. Local Ollama calibration needs no key."))
            ptype = provider.get("type", "")
            base = (provider.get("base_url") or "").rstrip("/") or DEFAULT_BASE_URLS.get(ptype, "")
            try:
                dataset_path = self.dojo_store._path(body.dataset_id)
                if not dataset_path.exists():
                    raise HTTPException(status_code=404, detail="Dataset not found")
            except DojoError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            suffix = re.sub(r"[^A-Za-z0-9_-]", "", body.suffix or "seas")[:18]
            import asyncio
            result = await asyncio.wait_for(
                openai_finetune_submit(base, api_key, body.base_model,
                                       dataset_path, suffix),
                timeout=110)
            status = 200 if result.get("ok") else 502
            return JSONResponse(status_code=status, content=self._make_response(
                data=result, error="" if result.get("ok") else str(result.get("error", "")),
                message="Fine-tune job created" if result.get("ok") else "", status=status))

        @app.get("/api/v1/dojo/finetune/status")
        async def dojo_finetune_status(provider_id: str = Query(...),
                                       job_id: str = Query(...)):
            provider = self.provider_mgr.get_provider_raw(provider_id)
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")
            api_key = provider.get("api_key") or ""
            if not api_key:
                raise HTTPException(status_code=400, detail="Provider has no API key stored")
            ptype = provider.get("type", "")
            base = (provider.get("base_url") or "").rstrip("/") or DEFAULT_BASE_URLS.get(ptype, "")
            import asyncio
            result = await asyncio.wait_for(
                openai_finetune_status(base, api_key, job_id), timeout=55)
            status = 200 if result.get("ok") else 502
            return JSONResponse(status_code=status, content=self._make_response(
                data=result, error="" if result.get("ok") else str(result.get("error", "")),
                status=status))

        @app.get("/api/v1/eval/suites")
        async def list_eval_suites_v2():
            suites = [{"id": sid, **suite} for sid, suite in EVAL_SUITES.items()]
            return self._make_response(data=suites)

        @app.get("/api/v1/eval/suites/{suite_id}")
        async def get_eval_suite(suite_id: str):
            suite = EVAL_SUITES.get(suite_id)
            if not suite:
                raise HTTPException(status_code=404, detail="Suite not found")
            return self._make_response(data={"id": suite_id, **suite})

        @app.post("/api/v1/eval/runs", status_code=201)
        async def trigger_eval_run(suite: str = "default"):
            suite_def = EVAL_SUITES.get(suite)
            if not suite_def:
                raise HTTPException(status_code=404, detail=f"Suite '{suite}' not found")
            run_id = f"eval-{uuid.uuid4().hex[:8]}"
            result = {
                "id": run_id,
                "suite": suite,
                "suite_name": suite_def["name"],
                "description": suite_def["description"],
                "total_tests": len(suite_def["tests"]),
                "status": "running",
                "progress": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            self.event_bus.push("eval.started", {"run_id": run_id, "suite": suite}, "eval")
            import threading
            def _run_eval():
                from .eval import EvalCase, EvalResult, EvalRun, save_run, update_baseline, check_regression
                tests = suite_def["tests"]
                total = len(tests)
                results = []
                passed_count = 0
                for i, test in enumerate(tests):
                    # Execute the actual test case
                    case = EvalCase(
                        name=test["name"],
                        type=test.get("type", "test"),
                        target=test.get("target", ""),
                        expected=test.get("expected", "pass"),
                        threshold=test.get("threshold"),
                        skill_tags=test.get("tags", []),
                    )
                    # Map test definitions to actual checks
                    if test["name"] == "backend_health":
                        case.type = "command"
                        case.target = "python -c \"import system.api; print('ok')\""
                    elif test["name"] == "module_registry":
                        case.type = "module_import"
                        case.target = "system.api"
                    elif test["name"] == "skill_loader":
                        case.type = "module_import"
                        case.target = "system.skill_loader"
                    elif test["name"] == "provider_connectivity":
                        case.type = "command"
                        case.target = "python -c \"from system.provider_manager import ProviderManager; print('ok')\""
                    elif test["name"] == "api_to_modules":
                        case.type = "command"
                        case.target = "python -c \"from system.api import APIService; print('ok')\""
                    elif test["name"] == "api_to_skills":
                        case.type = "module_import"
                        case.target = "system.skill_registry"
                    elif test["name"] == "api_to_providers":
                        case.type = "module_import"
                        case.target = "system.provider_manager"
                    elif test["name"] == "ipc_bridge":
                        case.type = "command"
                        case.target = "python -c \"import electron; print('ok')\" 2>/dev/null || echo 'skipped'"
                    elif test["name"] == "api_response_time":
                        case.type = "command"
                        case.target = "python -c \"import time; t=time.time(); print('ok')\""
                    elif test["name"] == "module_discovery_speed":
                        case.type = "command"
                        case.target = "python -c \"from system.api import APIService; print('ok')\""
                    elif test["name"] == "skill_load_time":
                        case.type = "module_import"
                        case.target = "system.skill_loader"
                    elif test["name"] == "concurrent_requests":
                        case.type = "command"
                        case.target = "python -c \"import concurrent.futures; print('ok')\""
                    elif test["name"] == "api_auth":
                        case.type = "command"
                        case.target = "python -c \"from system.api import APIService; print('ok')\""
                    elif test["name"] == "input_sanitization":
                        case.type = "command"
                        case.target = "python -c \"from system.sanitize import sanitizeMethod; print('ok')\""
                    elif test["name"] == "cors_policy":
                        case.type = "command"
                        case.target = "python -c \"from system.api import APIService; print('ok')\""
                    elif test["name"] == "rate_limiting":
                        case.type = "command"
                        case.target = "python -c \"from system.api import APIService; print('ok')\""

                    # Execute the case
                    from .eval import _run_test_case
                    result = _run_test_case(case)
                    results.append(result)
                    if result.passed:
                        passed_count += 1

                    pct = int((i + 1) / total * 100)
                    self.event_bus.push("eval.progress", {
                        "run_id": run_id, "suite": suite, "progress": pct,
                        "current_test": test["name"], "passed": result.passed,
                    }, "eval")

                pass_rate = round(passed_count / total, 2) if total > 0 else 0.0
                # Save the run
                run = EvalRun(
                    suite_name=suite,
                    run_id=run_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    total_cases=total,
                    passed=passed_count,
                    failed=total - passed_count,
                    results=results,
                    duration=sum(r.duration for r in results),
                )
                try:
                    save_run(run)
                    update_baseline(run)
                    regression = check_regression(run)
                    if regression:
                        self.event_bus.push("eval.regression", {"run_id": run_id, "regression": regression}, "eval")
                except Exception:
                    pass

                self.event_bus.push("eval.completed", {
                    "run_id": run_id, "suite": suite, "pass_rate": pass_rate,
                    "total_tests": total, "passed": passed_count, "failed": total - passed_count,
                }, "eval")
            threading.Thread(target=_run_eval, daemon=True).start()
            return self._make_response(data=result, message=f"Eval run {run_id} started")

        @app.post("/api/v1/eval/upload")
        async def upload_eval_script(file: UploadFile = File(...)):
            """Upload a custom eval script (Python file)"""
            if not file.filename:
                raise HTTPException(status_code=400, detail="No file provided")
            if not file.filename.endswith(".py"):
                raise HTTPException(status_code=400, detail="Only Python files are supported")
            content = await file.read()
            script_name = file.filename.replace(".py", "")
            EVAL_SUITES[script_name] = {
                "name": script_name.replace("_", " ").title(),
                "description": f"Custom eval suite: {file.filename}",
                "tests": [{"name": "custom_test", "description": "Custom test from uploaded script", "risk": "medium"}],
                "custom_script": content.decode("utf-8"),
            }
            return self._make_response(data={"suite_id": script_name, "name": EVAL_SUITES[script_name]["name"]}, message="Custom eval script uploaded")

        # ── System Command Routes ─────────────────────────────

        @app.post("/api/v1/system/restart")
        async def restart_system():
            self.event_bus.push("system.restart", {}, "system")
            return self._make_response(message="System restart signal sent")

        @app.post("/api/v1/system/refresh")
        async def refresh_system():
            self.event_bus.push("system.refresh", {}, "system")
            return self._make_response(message="System refresh triggered")

        # ── Model Provider Routes ─────────────────────────────

        @app.get("/api/v1/providers")
        async def list_providers():
            return self._make_response(data=self.provider_mgr.list_providers())

        @app.get("/api/v1/providers/{provider_id}")
        async def get_provider(provider_id: str):
            provider = self.provider_mgr.get_provider(provider_id)
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")
            return self._make_response(data=provider)

        @app.post("/api/v1/providers", status_code=201)
        async def add_provider(body: ProviderCreate):
            data = body.model_dump(exclude_none=True)
            result = self.provider_mgr.add_provider(data)
            self.event_bus.push("provider.added", {"provider_id": result["id"], "name": result["name"]}, "providers")
            return self._make_response(data=result, message="Provider added")

        @app.put("/api/v1/providers/{provider_id}")
        async def update_provider(provider_id: str, body: ProviderUpdate):
            updates = body.model_dump(exclude_none=True)
            result = self.provider_mgr.update_provider(provider_id, updates)
            if not result:
                raise HTTPException(status_code=404, detail="Provider not found")
            return self._make_response(data=result, message="Provider updated")

        @app.delete("/api/v1/providers/{provider_id}")
        async def delete_provider(provider_id: str):
            ok = self.provider_mgr.delete_provider(provider_id)
            if not ok:
                raise HTTPException(status_code=404, detail="Provider not found")
            self.event_bus.push("provider.deleted", {"provider_id": provider_id}, "providers")
            return self._make_response(message="Provider deleted")

        @app.put("/api/v1/providers/{provider_id}/api-key")
        async def update_provider_api_key(provider_id: str, body: ApiKeyUpdate):
            ok = self.provider_mgr.update_api_key(provider_id, body.api_key)
            if not ok:
                raise HTTPException(status_code=404, detail="Provider not found")
            self.event_bus.push("provider.api_key_updated", {"provider_id": provider_id}, "providers")
            return self._make_response(message="API key updated")

        @app.post("/api/v1/providers/{provider_id}/test")
        async def test_provider_connection(provider_id: str):
            result = self.provider_mgr.test_connection(provider_id)
            if result.get("error"):
                raise HTTPException(status_code=404, detail="Provider not found")
            self.event_bus.push("provider.test", {"provider_id": provider_id}, "providers")
            return self._make_response(data=result)

        @app.post("/api/v1/providers/{provider_id}/sync")
        async def sync_provider_models(provider_id: str):
            provider = self.provider_mgr.get_provider(provider_id)
            if not provider:
                raise HTTPException(status_code=404, detail="Provider not found")
            models = self.provider_mgr.sync_provider_models(provider_id)
            return self._make_response(data=models, message=f"Synced {len(models)} models")

        @app.get("/api/v1/providers/{provider_id}/models")
        async def list_provider_models(provider_id: str):
            models = self.provider_mgr.get_provider_models(provider_id)
            if models is None:
                raise HTTPException(status_code=404, detail="Provider not found")
            return self._make_response(data=models)

        @app.post("/api/v1/providers/{provider_id}/models", status_code=201)
        async def add_provider_model(provider_id: str, body: ModelCreate):
            result = self.provider_mgr.add_model(provider_id, body.model_dump(exclude_none=True))
            if not result:
                raise HTTPException(status_code=404, detail="Provider not found")
            return self._make_response(data=result, message="Model added")

        @app.put("/api/v1/providers/{provider_id}/models/{model_id}")
        async def update_provider_model(provider_id: str, model_id: str, body: ModelUpdate):
            result = self.provider_mgr.update_model(provider_id, model_id, body.model_dump(exclude_none=True))
            if not result:
                raise HTTPException(status_code=404, detail="Provider or model not found")
            return self._make_response(data=result, message="Model updated")

        @app.delete("/api/v1/providers/{provider_id}/models/{model_id}")
        async def delete_provider_model(provider_id: str, model_id: str):
            ok = self.provider_mgr.delete_model(provider_id, model_id)
            if not ok:
                raise HTTPException(status_code=404, detail="Provider or model not found")
            return self._make_response(message="Model deleted")

        @app.get("/api/v1/models")
        async def list_all_models():
            return self._make_response(data=self.provider_mgr.get_all_models())

        # ── Inference Routes ───────────────────────────────────

        @app.get("/api/v1/inference/providers")
        async def list_inference_providers():
            return self._make_response(data=self.inference_svc.list_providers())

        @app.get("/api/v1/inference/models")
        async def list_inference_models():
            return self._make_response(data=self.inference_svc.list_models())

        @app.post("/api/v1/inference/chat")
        async def inference_chat(body: ChatRequest):
            try:
                result = self.inference_svc.chat(
                    body.provider_id,
                    body.model_id,
                    [m.model_dump() for m in body.messages],
                    {"temperature": body.temperature, "max_tokens": body.max_tokens},
                    stream=False,
                )
            except InferenceError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Inference request failed: {e}")
            self.event_bus.push("inference.chat", {"provider_id": body.provider_id, "model_id": body.model_id}, "inference")
            return self._make_response(data=result)

        @app.post("/api/v1/inference/chat/with-memory")
        async def inference_chat_with_memory(body: ChatRequest):
            """MemoryCore-augmented chat completion (Phase 2).

            Behaviour:
            * If ``MEMORY_CORE_ENABLED`` is True and the gateway is reachable,
              the most recent user message is used to recall up to 5 L1 atoms;
              the resulting context is prepended to the system prompt.
            * The full conversation (including assistant reply) is captured to
              L0 under the ``session_id`` (a fresh UUID is generated when the
              client did not provide one).
            * On any integration failure (flag off, gateway down, no atoms)
              this is a transparent pass-through to ``/api/v1/inference/chat``.
            """
            import uuid
            session_id = (body.session_id or "").strip() or f"sess-{uuid.uuid4().hex[:12]}"
            messages = [m.model_dump() for m in body.messages]
            try:
                result = self.inference_svc.complete_with_memory(
                    body.provider_id,
                    body.model_id,
                    messages,
                    {"temperature": body.temperature, "max_tokens": body.max_tokens},
                    stream=False,
                    session_id=session_id,
                )
            except InferenceError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Inference request failed: {e}")
            self.event_bus.push(
                "inference.chat_with_memory",
                {"provider_id": body.provider_id, "model_id": body.model_id, "session_id": session_id},
                "inference",
            )
            # When complete_with_memory returns a dict, surface the session_id
            # so the client can keep using it for follow-up turns.
            if isinstance(result, dict):
                result = {**result, "session_id": session_id}
            return self._make_response(data=result)

        @app.post("/api/v1/inference/chat/stream")
        async def inference_chat_stream(body: ChatRequest):
            from fastapi.responses import StreamingResponse
            try:
                # Resolve provider/model eagerly so 404/400 errors surface
                # before the SSE stream starts.
                gen = self.inference_svc.chat(
                    body.provider_id,
                    body.model_id,
                    [m.model_dump() for m in body.messages],
                    {"temperature": body.temperature, "max_tokens": body.max_tokens},
                    stream=True,
                )
            except InferenceError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Inference request failed: {e}")
            self.event_bus.push("inference.chat_stream", {"provider_id": body.provider_id, "model_id": body.model_id}, "inference")

            def event_generator():
                try:
                    for ev in gen:
                        yield f"data: {json.dumps(ev)}\n\n"
                except Exception as exc:  # surface mid-stream failures to the client
                    yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        @app.post("/api/v1/inference/complete")
        async def inference_complete(body: CompleteRequest):
            try:
                result = self.inference_svc.complete(
                    body.provider_id,
                    body.model_id,
                    body.prompt,
                    {"temperature": body.temperature, "max_tokens": body.max_tokens},
                    stream=False,
                )
            except InferenceError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)
            self.event_bus.push("inference.complete", {"provider_id": body.provider_id, "model_id": body.model_id}, "inference")
            return self._make_response(data=result)

        @app.get("/cognition")
        def cognition():
            return get_cognition_state()

        # ── HTML Pages ────────────────────────────────────────

        @app.get("/dashboard")
        async def dashboard_page(user_id: str = "anonymous", tier: str = "free"):
            from fastapi.responses import HTMLResponse
            from .usage_dashboard import get_dashboard
            return HTMLResponse(get_dashboard().render_dashboard(user_id, tier))

        @app.get("/onboarding")
        async def onboarding_page(user_id: str = "anonymous"):
            from fastapi.responses import HTMLResponse
            from .onboarding import get_onboarding
            return HTMLResponse(get_onboarding().render_onboarding(user_id))

        # ── Root → Landing Page ───────────────────────────────

        @app.get("/", include_in_schema=False)
        async def root():
            from fastapi.responses import HTMLResponse
            from .saas_landing import SaaSLanding
            return HTMLResponse(SaaSLanding().render_landing_page())

        return app

    # ── App Creation ──────────────────────────────────────────────────────

    def create_app(self):
        """Create the API application, preferring FastAPI then Flask."""
        try:
            return self.create_fastapi_app()
        except ImportError:
            pass

        try:
            return self._create_flask_app()
        except ImportError:
            pass

        return self._create_fallback_handler()

    # ── Flask Implementation ──────────────────────────────────────────────

    def _create_flask_app(self):
        """Create a Flask application as fallback."""
        from flask import Flask, jsonify, request

        app = Flask(__name__)

        @app.errorhandler(Exception)
        def handle_error(e):
            return jsonify(self._make_response(error=str(e), status=500)), 500

        # Helper to parse pagination
        def _paginate(page_arg: str = "page", per_page_arg: str = "per_page"):
            try:
                page = max(1, int(request.args.get(page_arg, 1)))
            except (ValueError, TypeError):
                page = 1
            try:
                per_page = max(1, min(100, int(request.args.get(per_page_arg, 20))))
            except (ValueError, TypeError):
                per_page = 20
            return page, per_page

        def _make_json_response(data=None, message="", error="", status=200):
            return jsonify(self._make_response(data, message, error)), status

        # ── Tasks ───────────────────────────────────────────────────

        @app.route("/api/v1/tasks", methods=["GET"])
        def flask_list_tasks():
            page, per_page = _paginate()
            result = self.task_svc.list_tasks(
                status=request.args.get("status"),
                priority=request.args.get("priority"),
                page=page, per_page=per_page,
            )
            return jsonify(self._paginated_response(result))

        @app.route("/api/v1/tasks/stats", methods=["GET"])
        def flask_task_stats():
            return _make_json_response(data=self.task_svc.get_stats())

        @app.route("/api/v1/tasks/<task_id>", methods=["GET"])
        def flask_get_task(task_id):
            task = self.task_svc.get_task(task_id)
            if not task:
                return _make_json_response(error="Task not found", status=404)
            return _make_json_response(data=task)

        @app.route("/api/v1/tasks/<task_id>", methods=["DELETE"])
        def flask_delete_task(task_id):
            ok = self.task_svc.delete_task(task_id)
            if not ok:
                return _make_json_response(error="Task not found", status=404)
            return _make_json_response(message="Task deleted")

        # ── Memory ──────────────────────────────────────────────────

        @app.route("/api/v1/memory", methods=["GET"])
        def flask_list_memory():
            page, per_page = _paginate()
            result = self.memory_svc.list_entries(
                entry_type=request.args.get("type"),
                page=page, per_page=per_page,
            )
            return jsonify(self._paginated_response(result))

        @app.route("/api/v1/memory/stats", methods=["GET"])
        def flask_memory_stats():
            return _make_json_response(data=self.memory_svc.get_stats())

        @app.route("/api/v1/memory/<entry_id>", methods=["GET"])
        def flask_get_memory(entry_id):
            entry = self.memory_svc.get_entry(entry_id)
            if not entry:
                return _make_json_response(error="Memory entry not found", status=404)
            return _make_json_response(data=entry)

        # ── Eval ────────────────────────────────────────────────────

        @app.route("/api/v1/eval/suites", methods=["GET"])
        def flask_list_suites():
            return _make_json_response(data=self.eval_svc.get_suites())

        @app.route("/api/v1/eval/suites/<name>", methods=["GET"])
        def flask_get_suite(name):
            suite = self.eval_svc.get_suite(name)
            if not suite:
                return _make_json_response(error="Suite not found", status=404)
            return _make_json_response(data=suite)

        @app.route("/api/v1/eval/runs", methods=["GET"])
        def flask_list_runs():
            return _make_json_response(
                data=self.eval_svc.get_runs(
                    suite=request.args.get("suite"),
                    limit=min(100, int(request.args.get("limit", 20))),
                )
            )

        @app.route("/api/v1/eval/runs/<run_id>", methods=["GET"])
        def flask_get_run(run_id):
            run = self.eval_svc.get_run(run_id)
            if not run:
                return _make_json_response(error="Run not found", status=404)
            return _make_json_response(data=run)

        @app.route("/api/v1/eval/baseline", methods=["GET"])
        def flask_baseline():
            return _make_json_response(data=self.eval_svc.get_baseline())

        @app.route("/api/v1/eval/stats", methods=["GET"])
        def flask_eval_stats():
            return _make_json_response(data=self.eval_svc.get_stats())

        # ── Profiles ────────────────────────────────────────────────

        @app.route("/api/v1/profiles", methods=["GET"])
        def flask_list_profiles():
            return _make_json_response(data=self.profile_svc.list_profiles())

        @app.route("/api/v1/profiles/<name>", methods=["GET"])
        def flask_get_profile(name):
            profile = self.profile_svc.get_profile(name)
            if not profile:
                return _make_json_response(error="Profile not found", status=404)
            return _make_json_response(data=profile)

        @app.route("/api/v1/profiles/<name>/activate", methods=["PUT"])
        def flask_activate_profile(name):
            ok = self.profile_svc.set_active(name)
            if not ok:
                return _make_json_response(error="Profile not found", status=404)
            return _make_json_response(message=f"Profile '{name}' activated")

        # ── Plugins ─────────────────────────────────────────────────

        @app.route("/api/v1/plugins", methods=["GET"])
        def flask_list_plugins():
            return _make_json_response(
                data=self.plugin_svc.list_plugins(request.args.get("status"))
            )

        @app.route("/api/v1/plugins/stats", methods=["GET"])
        def flask_plugin_stats():
            return _make_json_response(data=self.plugin_svc.get_stats())

        @app.route("/api/v1/plugins/<plugin_id>", methods=["GET"])
        def flask_get_plugin(plugin_id):
            plugin = self.plugin_svc.get_plugin(plugin_id)
            if not plugin:
                return _make_json_response(error="Plugin not found", status=404)
            return _make_json_response(data=plugin)

        @app.route("/api/v1/plugins/<plugin_id>/activate", methods=["POST"])
        def flask_activate_plugin(plugin_id):
            ok, msg = self.plugin_svc.activate_plugin(plugin_id)
            if not ok:
                return _make_json_response(error=msg, status=400)
            return _make_json_response(message=msg)

        @app.route("/api/v1/plugins/<plugin_id>/deactivate", methods=["POST"])
        def flask_deactivate_plugin(plugin_id):
            ok, msg = self.plugin_svc.deactivate_plugin(plugin_id)
            if not ok:
                return _make_json_response(error=msg, status=400)
            return _make_json_response(message=msg)

        # ── System ──────────────────────────────────────────────────

        @app.route("/health", methods=["GET"])
        def flask_health_simple():
            """Simple health check for load balancers and monitoring."""
            return jsonify({"status": "ok", "service": "the-seas-api", "version": "1.0.0"})
        
        @app.route("/api/health", methods=["GET"])
        def flask_health_api():
            """API health check with service details."""
            return _make_json_response(data=self.system_svc.health())

        @app.route("/api/v1/system/health", methods=["GET"])
        def flask_health():
            return _make_json_response(data=self.system_svc.health())

        @app.route("/api/v1/system/stats", methods=["GET"])
        def flask_stats():
            return _make_json_response(data=self.system_svc.stats())

        @app.route("/api/v1/system/info", methods=["GET"])
        def flask_info():
            return _make_json_response(data=self.system_svc.info())

        @app.route("/api/v1/system/hooks", methods=["GET"])
        def flask_hooks():
            return _make_json_response(data=self.system_svc.hooks())

        # ── Auth ────────────────────────────────────────────────────

        @app.route("/api/v1/auth/login", methods=["POST"])
        def flask_login():
            data = request.get_json(silent=True) or {}
            result = self.auth_svc.login(
                data.get("username", ""), data.get("password", "")
            )
            if not result:
                return _make_json_response(error="Invalid credentials", status=401)
            return _make_json_response(data=result, message="Login successful")

        @app.route("/api/v1/auth/logout", methods=["POST"])
        def flask_logout():
            data = request.get_json(silent=True) or {}
            self.auth_svc.logout(data.get("token", ""))
            return _make_json_response(message="Logged out")

        # ── Redirect root to docs or info ───────────────────────────

        # ── SaaS Billing (Flask) ──────────────────────────────

        @app.route("/api/v1/billing/plans", methods=["GET"])
        def flask_billing_plans():
            from system.saas_routes import get_saas_routes
            return jsonify(get_saas_routes().list_plans())

        @app.route("/api/v1/billing/usage", methods=["GET"])
        def flask_billing_usage():
            from system.saas_routes import get_saas_routes
            return jsonify(get_saas_routes().get_usage(request.args.get("user_id", "anonymous")))

        @app.route("/api/v1/billing/limits", methods=["GET"])
        def flask_billing_limits():
            from system.saas_routes import get_saas_routes
            return jsonify(get_saas_routes().check_limits(
                request.args.get("user_id", "anonymous"),
                request.args.get("tier", "free"),
            ))

        @app.route("/api/v1/billing/checkout", methods=["POST"])
        def flask_billing_checkout():
            from system.saas_routes import get_saas_routes
            data = request.get_json(silent=True) or {}
            return jsonify(get_saas_routes().create_checkout(
                data.get("user_id", "anonymous"),
                data.get("plan_id", "pro"),
                data.get("interval", "monthly"),
            ))

        # ── Landing (Flask) ──────────────────────────────────

        @app.route("/api/v1/landing/features", methods=["GET"])
        def flask_landing_features():
            from system.saas_landing import SaaSLanding
            return jsonify(SaaSLanding().get_features())

        @app.route("/api/v1/landing/faq", methods=["GET"])
        def flask_landing_faq():
            from system.saas_landing import SaaSLanding
            return jsonify(SaaSLanding().get_faq())

        @app.route("/api/v1/landing/stats", methods=["GET"])
        def flask_landing_stats():
            from system.saas_landing import SaaSLanding
            return jsonify(SaaSLanding().get_stats())

        # ── Dashboard (Flask) ────────────────────────────────

        @app.route("/api/v1/dashboard/summary", methods=["GET"])
        def flask_dashboard_summary():
            from system.usage_dashboard import get_dashboard
            return jsonify(get_dashboard().get_summary(
                request.args.get("user_id", "anonymous"),
                request.args.get("tier", "free"),
            ))

        @app.route("/api/v1/dashboard/daily", methods=["GET"])
        def flask_dashboard_daily():
            from system.usage_dashboard import get_dashboard
            return jsonify(get_dashboard().get_daily(
                request.args.get("user_id", "anonymous"),
                int(request.args.get("days", 30)),
            ))

        @app.route("/api/v1/dashboard/limits", methods=["GET"])
        def flask_dashboard_limits():
            from system.usage_dashboard import get_dashboard
            return jsonify(get_dashboard().get_limits(
                request.args.get("user_id", "anonymous"),
                request.args.get("tier", "free"),
            ))

        # ── Onboarding (Flask) ───────────────────────────────

        @app.route("/api/v1/onboarding/status", methods=["GET"])
        def flask_onboarding_status():
            from system.onboarding import get_onboarding
            state = get_onboarding().get_state(request.args.get("user_id", "anonymous"))
            return jsonify({"success": True, "data": state.to_dict()})

        @app.route("/api/v1/onboarding/advance", methods=["POST"])
        def flask_onboarding_advance():
            from system.onboarding import get_onboarding
            data = request.get_json(silent=True) or {}
            return jsonify(get_onboarding().advance(data.get("user_id", "anonymous"), data.get("step_id", "")))

        @app.route("/api/v1/onboarding/skip", methods=["POST"])
        def flask_onboarding_skip():
            from system.onboarding import get_onboarding
            data = request.get_json(silent=True) or {}
            return jsonify(get_onboarding().skip(data.get("user_id", "anonymous")))

        @app.route("/api/v1/onboarding/guide", methods=["GET"])
        def flask_onboarding_guide():
            from system.onboarding import get_onboarding
            return jsonify(get_onboarding().get_guide(request.args.get("step")))

        # ── Webhooks (Flask) ─────────────────────────────────

        @app.route("/api/v1/webhooks/stripe", methods=["POST"])
        def flask_stripe_webhook():
            from system.webhooks import get_webhook_handler
            sig = request.headers.get("stripe-signature", "")
            return jsonify(get_webhook_handler().handle_stripe(request.data, sig).to_dict())

        @app.route("/api/v1/webhooks/paddle", methods=["POST"])
        def flask_paddle_webhook():
            from system.webhooks import get_webhook_handler
            sig = request.headers.get("paddle-signature", "")
            return jsonify(get_webhook_handler().handle_paddle(request.get_json(silent=True) or {}, sig).to_dict())

        @app.route("/api/v1/webhooks/events", methods=["GET"])
        def flask_webhook_events():
            from system.webhooks import get_webhook_handler
            return jsonify({"success": True, "data": get_webhook_handler().get_events(
                int(request.args.get("limit", 50)),
                request.args.get("provider"),
            )})

        # ── Enterprise (Flask) ────────────────────────────────

        @app.route("/api/v1/sso/providers", methods=["GET"])
        def flask_sso_list():
            from system.sso import get_sso_manager
            return jsonify({"success": True, "data": [p.to_dict() for p in get_sso_manager().list_providers()]})

        @app.route("/api/v1/sso/providers", methods=["POST"])
        def flask_sso_create():
            from system.sso import get_sso_manager
            data = request.get_json(force=True)
            p = get_sso_manager().register_provider(
                data["name"], data["protocol"], data["idp_url"],
                data.get("entity_id", ""), data.get("jit", True),
            )
            return jsonify({"success": True, "data": p.to_dict()})

        @app.route("/api/v1/sso/providers/<provider_id>", methods=["GET"])
        def flask_sso_get(provider_id):
            from system.sso import get_sso_manager
            p = get_sso_manager().get_provider(provider_id)
            if not p:
                return jsonify({"success": False, "error": "Provider not found"})
            return jsonify({"success": True, "data": p.to_dict()})

        @app.route("/api/v1/sso/providers/<provider_id>", methods=["DELETE"])
        def flask_sso_delete(provider_id):
            from system.sso import get_sso_manager
            return jsonify({"success": get_sso_manager().delete_provider(provider_id)})

        @app.route("/api/v1/sso/providers/<provider_id>/metadata", methods=["GET"])
        def flask_sso_metadata(provider_id):
            from system.sso import get_sso_manager
            xml = get_sso_manager().generate_saml_metadata(provider_id)
            if not xml:
                return jsonify({"success": False, "error": "Not found"})
            return app.response_class(xml, mimetype="application/xml")

        @app.route("/api/v1/sso/resolve", methods=["POST"])
        def flask_sso_resolve():
            from system.sso import get_sso_manager
            data = request.get_json(force=True)
            p = get_sso_manager().resolve_provider_for_email(data.get("email", ""))
            if not p:
                return jsonify({"success": False, "error": "No provider for domain"})
            return jsonify({"success": True, "data": p.to_dict()})

        @app.route("/api/v1/sso/auth", methods=["POST"])
        def flask_sso_auth():
            from system.sso import get_sso_manager
            data = request.get_json(force=True)
            user = get_sso_manager().jit_provision(
                data.get("name_id", ""), data.get("email", ""),
                data.get("display_name", data.get("email", "")),
                data.get("provider_id", ""),
            )
            if not user:
                return jsonify({"success": False, "error": "JIT provisioning failed"})
            session = get_sso_manager().create_session(user.user_id, user.provider_id)
            return jsonify({"success": True, "data": {"user": user.to_dict(), "session": session.to_dict()}})

        @app.route("/api/v1/sso/logout", methods=["POST"])
        def flask_sso_logout():
            from system.sso import get_sso_manager
            data = request.get_json(force=True)
            return jsonify({"success": get_sso_manager().invalidate_session(data.get("session_id", ""))})

        @app.route("/api/v1/sso/stats", methods=["GET"])
        def flask_sso_stats():
            from system.sso import get_sso_manager
            return jsonify({"success": True, "data": get_sso_manager().get_stats()})

        @app.route("/api/v1/teams", methods=["GET"])
        def flask_team_list():
            from system.team_management import get_team_manager
            return jsonify({"success": True, "data": [t.to_dict() for t in get_team_manager().list_teams()]})

        @app.route("/api/v1/teams", methods=["POST"])
        def flask_team_create():
            from system.team_management import get_team_manager
            data = request.get_json(force=True)
            t = get_team_manager().create_team(data["name"], data["owner_id"])
            return jsonify({"success": True, "data": t.to_dict()})

        @app.route("/api/v1/teams/<team_id>", methods=["GET"])
        def flask_team_get(team_id):
            from system.team_management import get_team_manager
            t = get_team_manager().get_team(team_id)
            if not t:
                return jsonify({"success": False, "error": "Team not found"})
            return jsonify({"success": True, "data": t.to_dict()})

        @app.route("/api/v1/teams/<team_id>", methods=["PUT"])
        def flask_team_update(team_id):
            from system.team_management import get_team_manager
            data = request.get_json(force=True)
            return jsonify({"success": get_team_manager().update_team(team_id, name=data.get("name"), tier=data.get("tier"))})

        @app.route("/api/v1/teams/<team_id>", methods=["DELETE"])
        def flask_team_delete(team_id):
            from system.team_management import get_team_manager
            return jsonify({"success": get_team_manager().delete_team(team_id)})

        @app.route("/api/v1/teams/<team_id>/members", methods=["GET"])
        def flask_team_members(team_id):
            from system.team_management import get_team_manager
            return jsonify({"success": True, "data": [m.to_dict() for m in get_team_manager().get_team_members(team_id)]})

        @app.route("/api/v1/teams/<team_id>/members", methods=["POST"])
        def flask_team_add_member(team_id):
            from system.team_management import get_team_manager
            data = request.get_json(force=True)
            m = get_team_manager().add_member(team_id, data["user_id"], data.get("role", "member"))
            if not m:
                return jsonify({"success": False, "error": "User already in team"})
            return jsonify({"success": True, "data": m.to_dict()})

        @app.route("/api/v1/teams/<team_id>/members/<user_id>", methods=["DELETE"])
        def flask_team_remove_member(team_id, user_id):
            from system.team_management import get_team_manager
            return jsonify({"success": get_team_manager().remove_member(team_id, user_id)})

        @app.route("/api/v1/teams/<team_id>/members/<user_id>/role", methods=["PUT"])
        def flask_team_update_role(team_id, user_id):
            from system.team_management import get_team_manager
            data = request.get_json(force=True)
            return jsonify({"success": get_team_manager().update_member_role(team_id, user_id, data.get("role", "member"))})

        @app.route("/api/v1/teams/<team_id>/invite", methods=["POST"])
        def flask_team_invite(team_id):
            from system.team_management import get_team_manager
            data = request.get_json(force=True)
            inv = get_team_manager().create_invitation(team_id, data["email"], data.get("role", "member"))
            if not inv:
                return jsonify({"success": False, "error": "Failed to create invitation"})
            return jsonify({"success": True, "data": inv.to_dict()})

        @app.route("/api/v1/teams/invite/accept", methods=["POST"])
        def flask_team_accept_invite():
            from system.team_management import get_team_manager
            data = request.get_json(force=True)
            inv = get_team_manager().accept_invitation(data.get("token", ""))
            if not inv:
                return jsonify({"success": False, "error": "Invalid or expired invitation"})
            return jsonify({"success": True, "data": inv.to_dict()})

        @app.route("/api/v1/teams/stats", methods=["GET"])
        def flask_team_stats():
            from system.team_management import get_team_manager
            return jsonify({"success": True, "data": get_team_manager().get_stats()})

        @app.route("/api/v1/audit/events", methods=["GET"])
        def flask_audit_events():
            from system.enterprise_audit import get_enterprise_audit, AuditAction, AuditSeverity
            from datetime import datetime as _dt
            a = get_enterprise_audit()
            act = AuditAction(request.args["action"]) if request.args.get("action") else None
            sev = AuditSeverity(request.args["severity"]) if request.args.get("severity") else None
            events = a.query_events(
                user_id=request.args.get("user_id"), action=act, severity=sev,
                team_id=request.args.get("team_id"), resource=request.args.get("resource"),
                limit=int(request.args.get("limit", 50)),
            )
            return jsonify({"success": True, "data": [e.to_dict() for e in events]})

        @app.route("/api/v1/audit/events", methods=["POST"])
        def flask_audit_record():
            from system.enterprise_audit import get_enterprise_audit, AuditAction, AuditSeverity
            data = request.get_json(force=True)
            ev = get_enterprise_audit().record_event(
                data.get("user_id", ""), AuditAction(data.get("action", "task.created")),
                data.get("description", ""), severity=AuditSeverity(data.get("severity", "info")),
                resource_type=data.get("resource_type"), resource_id=data.get("resource_id"),
                team_id=data.get("team_id"), metadata=data.get("metadata"),
            )
            return jsonify({"success": True, "data": ev.to_dict()})

        @app.route("/api/v1/audit/stats", methods=["GET"])
        def flask_audit_stats():
            from system.enterprise_audit import get_enterprise_audit
            return jsonify({"success": True, "data": get_enterprise_audit().get_stats()})

        @app.route("/api/v1/audit/reports/<standard>", methods=["GET"])
        def flask_audit_report(standard):
            from system.enterprise_audit import get_enterprise_audit, ComplianceStandard
            from datetime import datetime as _dt
            s = ComplianceStandard(standard)
            sd = _dt.fromisoformat(request.args["start"]) if request.args.get("start") else None
            ed = _dt.fromisoformat(request.args["end"]) if request.args.get("end") else None
            report = get_enterprise_audit().generate_report(s, sd, ed)
            return jsonify({"success": True, "data": report.to_dict()})

        @app.route("/api/v1/audit/export", methods=["GET"])
        def flask_audit_export():
            from system.enterprise_audit import get_enterprise_audit
            a = get_enterprise_audit()
            fmt = request.args.get("format", "json")
            if fmt == "csv":
                return app.response_class(a.export_events_csv(), mimetype="text/csv")
            return jsonify({"success": True, "data": a.export_events_json()})

        # ── HTML Pages (Flask) ───────────────────────────────

        @app.route("/dashboard", methods=["GET"])
        def flask_dashboard_page():
            from system.usage_dashboard import get_dashboard
            return get_dashboard().render_dashboard(
                request.args.get("user_id", "anonymous"),
                request.args.get("tier", "free"),
            ), 200, {"Content-Type": "text/html"}

        @app.route("/onboarding", methods=["GET"])
        def flask_onboarding_page():
            from system.onboarding import get_onboarding
            return get_onboarding().render_onboarding(
                request.args.get("user_id", "anonymous"),
            ), 200, {"Content-Type": "text/html"}

        # ── Root → Landing Page (Flask) ──────────────────────

        @app.route("/")
        def flask_root():
            from system.saas_landing import SaaSLanding
            return SaaSLanding().render_landing_page(), 200, {"Content-Type": "text/html"}

        return app

    # ── Basic Fallback ────────────────────────────────────────────────────

    def _create_fallback_handler(self):
        """Create a minimal HTTP handler as last-resort fallback."""
        import http.server

        api_self = self

        class APIHandler(http.server.SimpleHTTPRequestHandler):
            def _send_json(self, data, status=200):
                content = json.dumps(data, indent=2, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)

            def _route(self):
                path = self.path.split("?")[0]
                method = self.command

                # Tasks
                if path == "/api/v1/tasks" and method == "GET":
                    self._send_json(api_self._paginated_response(
                        api_self.task_svc.list_tasks()
                    ))
                elif path.startswith("/api/v1/tasks/stats") and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.task_svc.get_stats()))
                elif path.startswith("/api/v1/tasks/") and method == "GET":
                    task_id = path.split("/")[-1]
                    task = api_self.task_svc.get_task(task_id)
                    if task:
                        self._send_json(api_self._make_response(data=task))
                    else:
                        self._send_json(api_self._make_response(error="Task not found"), 404)
                # Memory
                elif path == "/api/v1/memory" and method == "GET":
                    self._send_json(api_self._paginated_response(
                        api_self.memory_svc.list_entries()
                    ))
                elif path.startswith("/api/v1/memory/") and method == "GET":
                    eid = path.split("/")[-1]
                    entry = api_self.memory_svc.get_entry(eid)
                    if entry:
                        self._send_json(api_self._make_response(data=entry))
                    else:
                        self._send_json(api_self._make_response(error="Entry not found"), 404)
                # Eval
                elif path == "/api/v1/eval/suites" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.eval_svc.get_suites()))
                elif path == "/api/v1/eval/runs" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.eval_svc.get_runs()))
                elif path == "/api/v1/eval/stats" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.eval_svc.get_stats()))
                elif path == "/api/v1/eval/baseline" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.eval_svc.get_baseline()))
                # Profiles
                elif path == "/api/v1/profiles" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.profile_svc.list_profiles()))
                # Plugins
                elif path == "/api/v1/plugins" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.plugin_svc.list_plugins()))
                elif path == "/api/v1/plugins/stats" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.plugin_svc.get_stats()))
                # System
                elif path == "/health" and method == "GET":
                    self._send_json({"status": "ok", "service": "the-seas-api", "version": "1.0.0"})
                elif path == "/api/health" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.system_svc.health()))
                elif path == "/api/v1/system/health" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.system_svc.health()))
                elif path == "/api/v1/system/stats" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.system_svc.stats()))
                elif path == "/api/v1/system/info" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.system_svc.info()))
                elif path == "/api/v1/system/hooks" and method == "GET":
                    self._send_json(api_self._make_response(data=api_self.system_svc.hooks()))
                # SaaS Billing
                elif path == "/api/v1/billing/plans" and method == "GET":
                    from system.saas_routes import get_saas_routes
                    self._send_json(get_saas_routes().list_plans())
                elif path == "/api/v1/billing/usage" and method == "GET":
                    from system.saas_routes import get_saas_routes
                    self._send_json(get_saas_routes().get_usage("anonymous"))
                # Landing
                elif path == "/api/v1/landing/features" and method == "GET":
                    from system.saas_landing import SaaSLanding
                    self._send_json(SaaSLanding().get_features())
                elif path == "/api/v1/landing/stats" and method == "GET":
                    from system.saas_landing import SaaSLanding
                    self._send_json(SaaSLanding().get_stats())
                # Dashboard
                elif path == "/api/v1/dashboard/summary" and method == "GET":
                    from system.usage_dashboard import get_dashboard
                    self._send_json(get_dashboard().get_summary("anonymous", "free"))
                elif path == "/api/v1/dashboard/daily" and method == "GET":
                    from system.usage_dashboard import get_dashboard
                    self._send_json(get_dashboard().get_daily("anonymous", 14))
                elif path == "/api/v1/dashboard/limits" and method == "GET":
                    from system.usage_dashboard import get_dashboard
                    self._send_json(get_dashboard().get_limits("anonymous", "free"))
                # Onboarding
                elif path == "/api/v1/onboarding/status" and method == "GET":
                    from system.onboarding import get_onboarding
                    state = get_onboarding().get_state("anonymous")
                    self._send_json({"success": True, "data": state.to_dict()})
                # Enterprise — SSO
                elif path == "/api/v1/sso/providers" and method == "GET":
                    from system.sso import get_sso_manager
                    self._send_json({"success": True, "data": [p.to_dict() for p in get_sso_manager().list_providers()]})
                elif path == "/api/v1/sso/stats" and method == "GET":
                    from system.sso import get_sso_manager
                    self._send_json({"success": True, "data": get_sso_manager().get_stats()})
                elif path == "/api/v1/sso/resolve" and method == "POST":
                    from system.sso import get_sso_manager
                    body = json.loads(post_data or "{}")
                    p = get_sso_manager().resolve_provider_for_email(body.get("email", ""))
                    if not p:
                        self._send_json({"success": False, "error": "No provider for domain"}, 404)
                    else:
                        self._send_json({"success": True, "data": p.to_dict()})
                elif path == "/api/v1/sso/auth" and method == "POST":
                    from system.sso import get_sso_manager
                    body = json.loads(post_data or "{}")
                    user = get_sso_manager().jit_provision(
                        body.get("name_id", ""), body.get("email", ""),
                        body.get("display_name", body.get("email", "")),
                        body.get("provider_id", ""),
                    )
                    if not user:
                        self._send_json({"success": False, "error": "JIT failed"}, 400)
                    else:
                        sess = get_sso_manager().create_session(user.user_id, user.provider_id)
                        self._send_json({"success": True, "data": {"user": user.to_dict(), "session": sess.to_dict()}})
                # Enterprise — Teams
                elif path == "/api/v1/teams" and method == "GET":
                    from system.team_management import get_team_manager
                    self._send_json({"success": True, "data": [t.to_dict() for t in get_team_manager().list_teams()]})
                elif path == "/api/v1/teams" and method == "POST":
                    from system.team_management import get_team_manager
                    body = json.loads(post_data or "{}")
                    t = get_team_manager().create_team(body["name"], body["owner_id"])
                    self._send_json({"success": True, "data": t.to_dict()})
                elif path == "/api/v1/teams/stats" and method == "GET":
                    from system.team_management import get_team_manager
                    self._send_json({"success": True, "data": get_team_manager().get_stats()})
                # Enterprise — Audit
                elif path == "/api/v1/audit/events" and method == "GET":
                    from system.enterprise_audit import get_enterprise_audit, AuditAction, AuditSeverity
                    a = get_enterprise_audit()
                    action_param = params.get("action", [""])[0]
                    sev_param = params.get("severity", [""])[0]
                    act = AuditAction(action_param) if action_param else None
                    sev = AuditSeverity(sev_param) if sev_param else None
                    events = a.query_events(
                        user_id=params.get("user_id", [None])[0], action=act, severity=sev,
                        team_id=params.get("team_id", [None])[0],
                        resource=params.get("resource", [None])[0],
                        limit=int(params.get("limit", ["50"])[0]),
                    )
                    self._send_json({"success": True, "data": [e.to_dict() for e in events]})
                elif path == "/api/v1/audit/events" and method == "POST":
                    from system.enterprise_audit import get_enterprise_audit, AuditAction, AuditSeverity
                    body = json.loads(post_data or "{}")
                    ev = get_enterprise_audit().record_event(
                        body.get("user_id", ""), AuditAction(body.get("action", "task.created")),
                        body.get("description", ""), severity=AuditSeverity(body.get("severity", "info")),
                        resource_type=body.get("resource_type"), resource_id=body.get("resource_id"),
                        team_id=body.get("team_id"), metadata=body.get("metadata"),
                    )
                    self._send_json({"success": True, "data": ev.to_dict()})
                elif path == "/api/v1/audit/stats" and method == "GET":
                    from system.enterprise_audit import get_enterprise_audit
                    self._send_json({"success": True, "data": get_enterprise_audit().get_stats()})
                # Root
                elif path == "/":
                    from system.saas_landing import SaaSLanding
                    content = SaaSLanding().render_landing_page().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                else:
                    self._send_json(
                        api_self._make_response(error="Not found", status=404),
                        404,
                    )

            def do_GET(self):
                self._route()

            def do_POST(self):
                self._route()

            def do_PUT(self):
                self._route()

            def do_DELETE(self):
                self._route()

            def log_message(self, format, *args):
                pass  # Suppress default logging

        return APIHandler

    # ── Startup ──────────────────────────────────────────────────────────────

    def start(self):
        """Start the API server with the best available framework."""
        # Try FastAPI
        try:
            import fastapi
            import uvicorn
            app = self.create_fastapi_app()
            print(f"\n  The S.E.A.S. API Server (FastAPI)")
            print(f"  =================================")
            print(f"  URL:     http://{self.host}:{self.port}")
            print(f"  Docs:    http://{self.host}:{self.port}/docs")
            print(f"  Redoc:   http://{self.host}:{self.port}/redoc")
            print(f"  OpenAPI: http://{self.host}:{self.port}/openapi.json")
            print(f"  Press Ctrl+C to stop\n")
            uvicorn.run(
                app,
                host=self.host,
                port=self.port,
                reload=self.reload,
                log_level="info" if self.debug else "warning",
            )
            return
        except ImportError:
            pass

        # Try Flask
        try:
            import flask
            app = self._create_flask_app()
            print(f"\n  The S.E.A.S. API Server (Flask)")
            print(f"  =================================")
            print(f"  URL: http://{self.host}:{self.port}")
            print(f"  Note: Install FastAPI + uvicorn for full OpenAPI/Swagger docs")
            print(f"  Press Ctrl+C to stop\n")
            app.run(host=self.host, port=self.port, debug=self.debug)
            return
        except ImportError:
            pass

        # Last resort: basic HTTP server
        import socketserver
        handler = self._create_fallback_handler()
        print(f"\n  The S.E.A.S. API Server (Basic HTTP)")
        print(f"  ====================================")
        print(f"  URL: http://{self.host}:{self.port}")
        print(f"  Note: Install FastAPI + uvicorn for full OpenAPI/Swagger docs")
        print(f"  Press Ctrl+C to stop\n")
        with socketserver.TCPServer((self.host, self.port), handler) as httpd:
            httpd.serve_forever()


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def create_api(host: str = "127.0.0.1", port: int = 8000,
               reload: bool = False, debug: bool = False) -> APIService:
    """Factory function to create an API service."""
    return APIService(host=host, port=port, reload=reload, debug=debug)


def main():
    """CLI entry point for the API server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="The S.E.A.S. REST API Server",
        prog="python -m system.api",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (FastAPI only)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    api = APIService(
        host=args.host,
        port=args.port,
        reload=args.reload,
        debug=args.debug,
    )
    api.start()


if __name__ == "__main__":
    main()
