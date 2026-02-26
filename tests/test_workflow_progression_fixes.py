"""
Targeted regression tests for workflow progression safeguards.
"""

from __future__ import annotations

import pytest

from agent_framework import ExecutorCompletedEvent, ExecutorInvokedEvent, WorkflowRunState, WorkflowStatusEvent

from orchestrator.agent_registry import AgentSelectionResult
from orchestrator.engine import OrchestratorEngine
from orchestrator.workflows import create_coordinator_workflow


def _agent(agent_id: str, name: str) -> AgentSelectionResult:
    return AgentSelectionResult(
        agent_id=agent_id,
        agent_name=name,
        short_name=name,
        category="specialist",
        included=True,
        reason="test",
        conditions_evaluated=["test"],
        priority=1,
        icon="",
        color="#000000",
        data_sources=[],
    )


@pytest.mark.asyncio
async def test_executor_completed_emits_agent_completed_on_repeated_runs():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-run", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("agent_a", "Agent A")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    await engine._process_workflow_event(ExecutorInvokedEvent("agent_a"))
    await engine._process_workflow_event(ExecutorCompletedEvent("agent_a"))
    await engine._process_workflow_event(ExecutorInvokedEvent("agent_a"))
    await engine._process_workflow_event(ExecutorCompletedEvent("agent_a"))

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 2
    assert completed[0]["executionCount"] == 1
    assert completed[1]["executionCount"] == 2


@pytest.mark.asyncio
async def test_loop_guard_emits_workflow_failed_and_raises():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-loop-guard",
        event_emitter=emit,
        enable_checkpointing=False,
        max_executor_invocations=1,
    )
    profile = _agent("agent_guard", "Agent Guard")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}
    engine._max_executor_invocations_effective = 1

    await engine._process_workflow_event(ExecutorInvokedEvent("agent_guard"))

    with pytest.raises(RuntimeError, match="handoff_loop_guard_triggered"):
        await engine._process_workflow_event(ExecutorInvokedEvent("agent_guard"))

    failed_events = [p for t, p in captured if t == "workflow.failed"]
    assert failed_events, "workflow.failed should be emitted when loop guard triggers"
    assert failed_events[-1]["reason"] == "handoff_loop_guard_triggered"
    assert failed_events[-1]["loopGuardTriggered"] is True


@pytest.mark.asyncio
async def test_workflow_status_event_includes_workflow_state():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-status", event_emitter=emit, enable_checkpointing=False)

    await engine._process_workflow_event(WorkflowStatusEvent(WorkflowRunState.IDLE))

    status_events = [p for t, p in captured if t == "workflow.status"]
    assert len(status_events) == 1
    assert status_events[0]["workflowState"] == "IDLE"


def test_coordinator_workflow_constrains_handoff_targets_and_turn_limits():
    workflow = create_coordinator_workflow(
        scenario="hub_disruption",
        active_agent_ids=[
            "situation_assessment",
            "fleet_recovery",
            "crew_recovery",
            "network_impact",
            "weather_safety",
            "passenger_impact",
            "recovery_coordinator",
        ],
    )

    coordinator_id = "recovery_coordinator"
    specialist_ids = {
        "situation_assessment",
        "fleet_recovery",
        "crew_recovery",
        "network_impact",
        "weather_safety",
        "passenger_impact",
    }

    coordinator_executor = workflow.executors[coordinator_id]
    assert getattr(coordinator_executor, "_handoff_targets") == specialist_ids
    assert getattr(coordinator_executor, "_autonomous_mode_turn_limit") == 8

    for specialist_id in specialist_ids:
        specialist_executor = workflow.executors[specialist_id]
        assert getattr(specialist_executor, "_handoff_targets") == {coordinator_id}
        assert getattr(specialist_executor, "_autonomous_mode_turn_limit") == 2
