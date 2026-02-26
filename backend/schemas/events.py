"""
Workflow event schemas for SSE streaming.
Events are published to Redis Streams and consumed by the SSE endpoint.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class EventLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class EventKind(str, Enum):
    # Lifecycle events
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"

    # Stage events
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"

    # Agent events
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_STARTED_DOT = "agent.started"
    AGENT_COMPLETED_DOT = "agent.completed"
    AGENT_OBJECTIVE = "agent.objective"
    AGENT_PROGRESS = "agent.progress"

    # Tool events
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    TOOL_CALLED_DOT = "tool.called"
    TOOL_COMPLETED_DOT = "tool.completed"
    TOOL_FAILED_DOT = "tool.failed"

    # Executor-level events
    EXECUTOR_INVOKED = "executor.invoked"
    EXECUTOR_COMPLETED = "executor.completed"

    # Orchestrator events
    ORCHESTRATOR_PLAN = "orchestrator.plan"
    ORCHESTRATOR_DELEGATED = "orchestrator.delegated"
    ORCHESTRATOR_DECISION = "orchestrator.decision"
    WORKFLOW_STATUS = "workflow.status"

    # Agent detail events
    AGENT_STATUS = "agent.status"
    AGENT_EVIDENCE = "agent.evidence"
    AGENT_REASONING = "agent.reasoning"
    AGENT_STREAMING = "agent.streaming"

    # NEW: Agent lifecycle for canvas UI
    AGENT_ACTIVATED = "agent.activated"
    AGENT_EXCLUDED = "agent.excluded"
    AGENT_RECOMMENDATION = "agent.recommendation"
    SPAN_STARTED = "span.started"
    SPAN_ENDED = "span.ended"

    # NEW: Data source activity
    DATA_SOURCE_QUERY_START = "data_source.query_start"
    DATA_SOURCE_QUERY_COMPLETE = "data_source.query_complete"

    # NEW: Coordinator output
    COORDINATOR_SCORING = "coordinator.scoring"
    COORDINATOR_PLAN = "coordinator.plan"

    # NEW: Recovery artifacts
    RECOVERY_OPTION = "recovery.option"

    # NEW: Agent-to-agent handover
    HANDOVER = "handover"

    # Progress events
    PROGRESS_UPDATE = "progress_update"
    HEARTBEAT = "heartbeat"


class WorkflowEvent(BaseModel):
    """Event schema for real-time workflow progress streaming."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = Field(description="Workflow run identifier")
    stream_id: Optional[str] = Field(default=None, description="Redis stream message id for resume")

    ts: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    sequence: int = Field(default=0, description="Event sequence number within run")

    level: EventLevel = Field(default=EventLevel.INFO)
    kind: EventKind = Field(description="Event type")

    stage_id: Optional[str] = Field(default=None)
    stage_name: Optional[str] = Field(default=None)

    agent_name: Optional[str] = Field(default=None)
    executor_name: Optional[str] = Field(default=None)
    tool_name: Optional[str] = Field(default=None)

    message: str = Field(description="Short human-readable message")
    payload: Dict[str, Any] = Field(default_factory=dict)
    actor: Dict[str, Any] = Field(default_factory=dict, description="Actor metadata for UI rendering")

    trace_id: Optional[str] = Field(default=None)
    span_id: Optional[str] = Field(default=None)
    parent_span_id: Optional[str] = Field(default=None)

    progress_pct: Optional[float] = Field(default=None, ge=0, le=100)
    duration_ms: Optional[int] = Field(default=None)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def to_sse_data(self) -> str:
        return self.model_dump_json()


def heartbeat_event(run_id: str, sequence: int = 0) -> WorkflowEvent:
    return WorkflowEvent(
        run_id=run_id, kind=EventKind.HEARTBEAT,
        sequence=sequence, message="heartbeat",
    )


def stage_started_event(run_id: str, stage_id: str, stage_name: str, sequence: int = 0) -> WorkflowEvent:
    return WorkflowEvent(
        run_id=run_id, kind=EventKind.STAGE_STARTED,
        stage_id=stage_id, stage_name=stage_name,
        sequence=sequence, message=f"Stage '{stage_name}' started",
    )


def stage_completed_event(run_id: str, stage_id: str, stage_name: str, duration_ms: int, sequence: int = 0) -> WorkflowEvent:
    return WorkflowEvent(
        run_id=run_id, kind=EventKind.STAGE_COMPLETED,
        stage_id=stage_id, stage_name=stage_name,
        sequence=sequence, duration_ms=duration_ms,
        message=f"Stage '{stage_name}' completed in {duration_ms}ms",
    )


def tool_called_event(run_id: str, tool_name: str, agent_name: str, sequence: int = 0) -> WorkflowEvent:
    return WorkflowEvent(
        run_id=run_id, kind=EventKind.TOOL_CALLED,
        tool_name=tool_name, agent_name=agent_name,
        sequence=sequence, message=f"Tool '{tool_name}' called by {agent_name}",
    )
