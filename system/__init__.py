"""
S.E.A.S. System — Demo version core engine.
Minimal __init__.py for demo purposes only.
"""

__version__ = "1.0.0-demo"

from .models import Task, TaskStatus, RiskLevel, Priority, AgentStatus

# Core skill system
from .skill_registry import SkillRegistry, Skill
from .skill_loader import SkillLoader

# CRM interface
from .crm_repository import CrmRepository, MockCrmRepository, SearchResult

# Capability system
from .capabilities import Capability, enabled, unavailable

# Inference
from .inference_service import InferenceService, get_inference_service

__all__ = [
    "Task",
    "TaskStatus",
    "RiskLevel", 
    "Priority",
    "AgentStatus",
    "SkillRegistry",
    "Skill",
    "SkillLoader",
    "CrmRepository",
    "MockCrmRepository",
    "SearchResult",
    "Capability",
    "enabled",
    "unavailable",
    "InferenceService",
    "get_inference_service",
]