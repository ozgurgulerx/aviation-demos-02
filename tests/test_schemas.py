"""
Tests for Pydantic schemas: events and runs.
"""

import json
import pytest
from schemas.events import (
    EventKind,
    EventLevel,
    WorkflowEvent,
    heartbeat_event,
    stage_started_event,
    stage_completed_event,
    tool_called_event,
)
from schemas.runs import (
    RunStatus,
    StageStatus,
    StageMetadata,
    RunMetadata,
    create_new_run,
    DEFAULT_STAGES,
)


class TestEventKind:
    def test_lifecycle_events_exist(self):
        assert EventKind.RUN_STARTED == "run_started"
        assert EventKind.RUN_COMPLETED == "run_completed"
        assert EventKind.RUN_FAILED == "run_failed"

    def test_stage_events_exist(self):
        assert EventKind.STAGE_STARTED == "stage_started"
        assert EventKind.STAGE_COMPLETED == "stage_completed"
        assert EventKind.STAGE_FAILED == "stage_failed"

    def test_agent_events_exist(self):
        assert EventKind.AGENT_STARTED == "agent_started"
        assert EventKind.AGENT_COMPLETED == "agent_completed"
        assert EventKind.AGENT_STARTED_DOT == "agent.started"
        assert EventKind.AGENT_COMPLETED_DOT == "agent.completed"
        assert EventKind.AGENT_OBJECTIVE == "agent.objective"
        assert EventKind.AGENT_PROGRESS == "agent.progress"

    def test_tool_events_exist(self):
        assert EventKind.TOOL_CALLED == "tool_called"
        assert EventKind.TOOL_COMPLETED == "tool_completed"
        assert EventKind.TOOL_CALLED_DOT == "tool.called"
        assert EventKind.TOOL_COMPLETED_DOT == "tool.completed"
        assert EventKind.TOOL_FAILED_DOT == "tool.failed"

    def test_heartbeat_exists(self):
        assert EventKind.HEARTBEAT == "heartbeat"


class TestWorkflowEvent:
    def test_create_minimal_event(self):
        event = WorkflowEvent(
            run_id="test-run-123",
            kind=EventKind.RUN_STARTED,
            message="Run started",
        )
        assert event.run_id == "test-run-123"
        assert event.kind == EventKind.RUN_STARTED
        assert event.level == EventLevel.INFO
        assert event.event_id  # auto-generated
        assert event.ts  # auto-generated
        assert event.sequence == 0

    def test_event_serialization(self):
        event = WorkflowEvent(
            run_id="test-run",
            kind=EventKind.TOOL_CALLED,
            message="Calling analyze_flight_data",
            tool_name="analyze_flight_data",
            agent_name="flight_analyst",
        )
        data = json.loads(event.to_sse_data())
        assert data["run_id"] == "test-run"
        assert data["kind"] == "tool_called"
        assert data["tool_name"] == "analyze_flight_data"
        assert data["agent_name"] == "flight_analyst"

    def test_event_with_payload(self):
        event = WorkflowEvent(
            run_id="test-run",
            kind=EventKind.PROGRESS_UPDATE,
            message="50% done",
            payload={"progress": 50, "current_step": "analysis"},
        )
        assert event.payload["progress"] == 50

    def test_event_envelope_fields(self):
        event = WorkflowEvent(
            run_id="test-run",
            kind=EventKind.AGENT_PROGRESS,
            message="agent progressing",
            actor={"kind": "agent", "id": "flight_analyst", "name": "Flight Analyst"},
            trace_id="abc",
            span_id="def",
            parent_span_id="ghi",
            stream_id="1740000000000-1",
        )
        data = json.loads(event.to_sse_data())
        assert data["actor"]["kind"] == "agent"
        assert data["trace_id"] == "abc"
        assert data["stream_id"] == "1740000000000-1"


class TestEventFactories:
    def test_heartbeat_event(self):
        event = heartbeat_event(run_id="run-1", sequence=5)
        assert event.kind == EventKind.HEARTBEAT
        assert event.run_id == "run-1"
        assert event.sequence == 5
        assert event.message == "heartbeat"

    def test_stage_started_event(self):
        event = stage_started_event(
            run_id="run-1",
            stage_id="flight_analysis",
            stage_name="Flight Analysis",
            sequence=1,
        )
        assert event.kind == EventKind.STAGE_STARTED
        assert event.stage_id == "flight_analysis"
        assert "Flight Analysis" in event.message

    def test_stage_completed_event(self):
        event = stage_completed_event(
            run_id="run-1",
            stage_id="flight_analysis",
            stage_name="Flight Analysis",
            duration_ms=1500,
        )
        assert event.kind == EventKind.STAGE_COMPLETED
        assert event.duration_ms == 1500

    def test_tool_called_event(self):
        event = tool_called_event(
            run_id="run-1",
            tool_name="check_weather_impact",
            agent_name="flight_analyst",
        )
        assert event.kind == EventKind.TOOL_CALLED
        assert event.tool_name == "check_weather_impact"
        assert event.agent_name == "flight_analyst"


class TestRunMetadata:
    def test_create_new_run(self):
        run = create_new_run(problem_description="Test problem")
        assert run.status == RunStatus.PENDING
        assert run.problem_description == "Test problem"
        assert run.run_id  # auto-generated
        assert len(run.stages) == 3
        assert run.total_stages == 3

    def test_default_stages(self):
        assert len(DEFAULT_STAGES) == 3
        stage_names = [s.stage_name for s in DEFAULT_STAGES]
        assert "Flight Analysis" in stage_names
        assert "Operations Optimization" in stage_names
        assert "Safety Inspection" in stage_names

    def test_run_progress_calculation(self):
        run = create_new_run()
        assert run.progress_pct == 0

        # Complete first stage
        run.stages[0].status = StageStatus.SUCCEEDED
        run.update_progress()
        assert run.stages_completed == 1
        assert pytest.approx(run.progress_pct, 0.1) == 33.3

        # Complete all stages
        for stage in run.stages:
            stage.status = StageStatus.SUCCEEDED
        run.update_progress()
        assert run.stages_completed == 3
        assert run.progress_pct == 100

    def test_stage_metadata(self):
        stage = StageMetadata(
            stage_id="test_stage",
            stage_name="Test Stage",
            stage_order=1,
        )
        assert stage.status == StageStatus.PENDING
        assert stage.progress_pct == 0
        assert stage.duration_ms is None


class TestRunStatus:
    def test_all_statuses(self):
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.CANCELLED == "cancelled"
