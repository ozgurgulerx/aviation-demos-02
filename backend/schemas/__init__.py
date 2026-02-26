"""
Aviation Multi-Agent Solver Schemas - Pydantic models for workflow artifacts.
"""

from .events import (
    WorkflowEvent,
    EventLevel,
    EventKind,
    heartbeat_event,
)

from .runs import (
    RunStatus,
    RunMetadata,
    StageStatus,
    StageMetadata,
)

__all__ = [
    # Events
    "WorkflowEvent",
    "EventLevel",
    "EventKind",
    "heartbeat_event",
    # Runs
    "RunStatus",
    "RunMetadata",
    "StageStatus",
    "StageMetadata",
]
