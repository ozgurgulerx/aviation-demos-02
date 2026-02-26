"""
Run and stage metadata schemas for workflow state management.
Stored in PostgreSQL for durability.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class RunStatus(str, Enum):
    """Workflow run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    """Individual stage status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageMetadata(BaseModel):
    """Metadata for a single workflow stage."""
    stage_id: str = Field(description="Unique stage identifier")
    stage_name: str = Field(description="Human-readable stage name")
    stage_order: int = Field(description="Execution order")

    status: StageStatus = Field(default=StageStatus.PENDING)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    progress_pct: float = Field(default=0, ge=0, le=100)
    error_message: Optional[str] = None


class RunMetadata(BaseModel):
    """Complete metadata for a workflow run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique run identifier")
    status: RunStatus = Field(default=RunStatus.PENDING)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    # Configuration
    problem_description: str = Field(default="", description="Problem submitted by user")
    config: Dict[str, Any] = Field(default_factory=dict, description="Run configuration")

    # Progress
    current_stage: Optional[str] = Field(default=None)
    stages_completed: int = Field(default=0)
    total_stages: int = Field(default=3)
    progress_pct: float = Field(default=0, ge=0, le=100)

    # Stage details
    stages: List[StageMetadata] = Field(default_factory=list)

    # Error handling
    error_message: Optional[str] = None
    error_stage: Optional[str] = None

    # Audit
    event_count: int = Field(default=0)
    last_event_at: Optional[datetime] = None

    def update_progress(self):
        """Recalculate progress from stage completion."""
        if not self.stages:
            self.progress_pct = 0
            return
        completed = sum(
            1 for s in self.stages
            if s.status in [StageStatus.SUCCEEDED, StageStatus.SKIPPED]
        )
        self.stages_completed = completed
        self.progress_pct = (completed / len(self.stages)) * 100


# Default stages for aviation solver
DEFAULT_STAGES = [
    StageMetadata(stage_id="flight_analysis", stage_name="Flight Analysis", stage_order=1),
    StageMetadata(stage_id="operations_optimization", stage_name="Operations Optimization", stage_order=2),
    StageMetadata(stage_id="safety_inspection", stage_name="Safety Inspection", stage_order=3),
]


def create_new_run(problem_description: str = "", config: Dict[str, Any] = None) -> RunMetadata:
    """Factory function to create a new run with default stages."""
    return RunMetadata(
        problem_description=problem_description,
        config=config or {},
        stages=[stage.model_copy(deep=True) for stage in DEFAULT_STAGES],
    )
