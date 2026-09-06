"""Task and goal data models."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class RateLimitError(Exception):
    """Raised when a rate limit is exceeded."""
    pass


class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Priority(str, Enum):
    P0 = "P0"  # Blocker
    P1 = "P1"  # Critical
    P2 = "P2"  # Important
    P3 = "P3"  # Nice to have


class AgentStatus(str, Enum):
    """Status of a sub-agent in the orchestration system."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# CRM Task Kinds — from integration_roadmap.md Phase 1
# ---------------------------------------------------------------------------

class CrmTaskKind(str, Enum):
    """Task kinds specific to CRM enrichment workflows."""

    IDENTITY = "identity"           # Contact identity verification
    PROFILE = "profile"             # Contact profile enrichment
    RECHECK = "recheck"             # Scheduled recheck of stale data
    MEETING_PREP = "meeting_prep"   # Meeting preparation research
    COMPANY_PROFILE = "company_profile"  # Company profile enrichment
    WORKSPACE_PROFILE = "workspace_profile"  # Workspace self-profile
    BRAND = "brand"                 # Company brand enrichment
    PORTRAIT = "portrait"           # Contact portrait generation


class OrchestrationPattern(str, Enum):
    """Pattern for orchestrating multiple sub-agents."""
    FAN_OUT_FAN_IN = "fan_out_fan_in"
    PIPELINE = "pipeline"
    COMPETITIVE = "competitive"
    CONSENSUS = "consensus"


@dataclass
class VerificationPlan:
    """What must be checked before a task can be marked complete."""
    method: str           # e.g.  "test", "type_check", "output_inspection", "human_approval"
    command: str          # The command or check to run
    expected_outcome: str # What success looks like
    evidence_path: Optional[str] = None  # Where evidence will be saved


@dataclass
class Task:
    """A single unit of work in the task graph."""
    description: str
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"t-{uuid.uuid4().hex[:8]}"
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.P2
    risk_level: RiskLevel = RiskLevel.LOW
    depends_on: list[str] = field(default_factory=list)
    skill_tags: list[str] = field(default_factory=list)
    owner: Optional[str] = None
    verification_plan: Optional[VerificationPlan] = None
    evidence: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    budget_limit: Optional[float] = None
    tokens_used: int = 0
    cost: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    failure_reason: Optional[str] = None
    escalation_reason: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["verification_plan"] = asdict(self.verification_plan) if self.verification_plan else None
        result["status"] = self.status.value
        result["priority"] = self.priority.value
        result["risk_level"] = self.risk_level.value
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        if data.get("verification_plan"):
            data["verification_plan"] = VerificationPlan(**data["verification_plan"])
        if "status" in data:
            data["status"] = TaskStatus(data["status"])
        if "priority" in data:
            data["priority"] = Priority(data["priority"])
        if "risk_level" in data:
            data["risk_level"] = RiskLevel(data["risk_level"])
        return cls(**data)


@dataclass
class Goal:
    """A high-level objective that decomposes into a task graph."""
    id: str
    description: str
    tasks: list[str] = field(default_factory=list)  # Task IDs
    status: str = "active"  # active, completed, failed, cancelled
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    total_cost: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        return cls(**data)


@dataclass
class MemoryEntry:
    """A recorded memory entry (learning, decision or observation)."""
    id: str
    entry_type: str  # "learning", "decision", "observation", "failure"
    content: str
    tags: list[str] = field(default_factory=list)
    source_task_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(**data)
