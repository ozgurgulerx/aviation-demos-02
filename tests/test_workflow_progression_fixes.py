"""
Targeted regression tests for workflow progression safeguards.
"""

from __future__ import annotations

import asyncio
import pytest

from agent_framework import ExecutorCompletedEvent, ExecutorInvokedEvent, WorkflowRunState, WorkflowStatusEvent

from orchestrator.agent_registry import AgentSelectionResult, SCENARIO_AGENTS
from orchestrator.engine import OrchestratorEngine
from orchestrator.trace_emitter import TraceEmitter
from orchestrator.workflows import (
    OrchestrationMode,
    WorkflowType,
    create_coordinator_workflow,
    create_deterministic_coordinator_workflow,
    create_workflow,
)


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


def test_deterministic_workflow_orders_specialists_then_coordinator():
    scenario = "diversion"
    scenario_config = SCENARIO_AGENTS[scenario]
    workflow = create_deterministic_coordinator_workflow(
        scenario=scenario,
        active_agent_ids=scenario_config["agents"] + [scenario_config["coordinator"]],
    )

    expected_order = scenario_config["agents"] + [scenario_config["coordinator"]]
    execution_order = [
        executor_id
        for executor_id in workflow.executors.keys()
        if executor_id not in {"input-conversation", "output-conversation", "end"}
    ]
    assert execution_order == expected_order

    for executor in workflow.executors.values():
        assert getattr(executor, "_handoff_targets", set()) in (set(), None)


def test_workflow_factory_routes_handoff_modes():
    problem = "Need a diversion plan to an alternate airport due to severe weather."
    scenario = "diversion"
    coordinator_id = SCENARIO_AGENTS[scenario]["coordinator"]

    default_workflow = create_workflow(
        workflow_type=WorkflowType.HANDOFF,
        problem=problem,
    )
    llm_directed_workflow = create_workflow(
        workflow_type=WorkflowType.HANDOFF,
        problem=problem,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
    )
    deterministic_workflow = create_workflow(
        workflow_type=WorkflowType.HANDOFF,
        problem=problem,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
    )
    mesh_workflow = create_workflow(
        workflow_type=WorkflowType.HANDOFF,
        problem=problem,
        orchestration_mode=OrchestrationMode.HANDOFF_MESH,
    )

    assert getattr(default_workflow.executors[coordinator_id], "_handoff_targets", set()) in (set(), None)
    assert getattr(llm_directed_workflow.executors[coordinator_id], "_handoff_targets", set()) in (set(), None)
    assert getattr(deterministic_workflow.executors[coordinator_id], "_handoff_targets", set()) in (set(), None)
    assert len(getattr(mesh_workflow.executors[coordinator_id], "_handoff_targets")) >= 1


@pytest.mark.asyncio
async def test_coordinator_structured_output_emits_scoring_option_and_plan():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-artifacts",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )
    engine.trace_emitter = TraceEmitter(run_id="test-artifacts", event_callback=emit)

    structured_response = """Coordinator synthesis complete.
```json
{
  "criteria": ["delay_reduction", "crew_margin", "safety_score", "cost_impact", "passenger_impact"],
  "options": [
    {
      "optionId": "opt-1",
      "description": "Swap tail and rebalance crew pairings",
      "rank": 1,
      "scores": {"delay_reduction": 84, "crew_margin": 78, "safety_score": 92, "cost_impact": 63, "passenger_impact": 81}
    },
    {
      "optionId": "opt-2",
      "description": "Delay bank and protect long-haul departures",
      "rank": 2,
      "scores": {"delay_reduction": 69, "crew_margin": 74, "safety_score": 90, "cost_impact": 72, "passenger_impact": 66}
    }
  ],
  "selectedOptionId": "opt-1",
  "summary": "Recommend opt-1 to minimize network knock-on delays with acceptable cost.",
  "timeline": [
    {"time": "T+0", "action": "Dispatch swaps", "agent": "fleet_recovery"},
    {"time": "T+15m", "action": "Crew legality refresh", "agent": "crew_recovery"}
  ]
}
```
"""

    await engine._emit_coordinator_artifacts(structured_response)

    event_types = [event_type for event_type, _ in captured]
    assert event_types.count("recovery.option") == 2
    assert "coordinator.scoring" in event_types
    assert "coordinator.plan" in event_types


@pytest.mark.asyncio
async def test_coordinator_malformed_output_still_emits_plan():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-artifacts-fallback",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )
    engine.trace_emitter = TraceEmitter(run_id="test-artifacts-fallback", event_callback=emit)

    malformed_response = "Recommendation: prioritize crew legality first then optimize tail swaps. T+0: stabilize schedule."
    await engine._emit_coordinator_artifacts(malformed_response)

    plan_events = [payload for event_type, payload in captured if event_type == "coordinator.plan"]
    assert len(plan_events) == 1
    assert plan_events[0].get("summary")


@pytest.mark.asyncio
async def test_deterministic_timeout_emits_failed_reason(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-deterministic-timeout",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )
    engine._deterministic_execution_timeout_seconds = 0.01

    async def _slow_stream(_input_message: str):
        await asyncio.sleep(0.2)
        return {"status": "completed"}

    monkeypatch.setattr(engine, "_stream_workflow", _slow_stream)

    with pytest.raises(RuntimeError, match="deterministic_execution_timeout"):
        await engine._execute_workflow_with_events("test input")

    failed = [payload for event_type, payload in captured if event_type == "workflow.failed"]
    assert failed
    assert failed[-1]["reason"] == "deterministic_execution_timeout"


@pytest.mark.asyncio
async def test_llm_directed_selection_applies_agent_order(monkeypatch):
    engine = OrchestratorEngine(
        run_id="test-llm-directed-selection",
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    engine.scenario = "diversion"

    async def fake_plan(**kwargs):
        return {
            "selectedAgentIds": ["route_planner", "weather_safety", "decision_coordinator"],
            "executionOrder": ["weather_safety", "route_planner", "decision_coordinator"],
            "coordinatorAgentId": "decision_coordinator",
            "excludedAgentIds": ["real_time_monitor"],
            "reasoning": "Need weather and routing specialists with coordinator synthesis.",
            "confidence": 0.89,
            "agentReasons": {
                "weather_safety": "Assess weather constraints first.",
                "route_planner": "Compute alternate routing options.",
            },
        }

    monkeypatch.setattr(engine, "_llm_plan_agent_selection", fake_plan)
    await engine._select_agents("Need immediate diversion routing under deteriorating weather.")

    selected_ids = [agent.agent_id for agent in engine.selected_agents]
    assert selected_ids == ["weather_safety", "route_planner", "decision_coordinator"]
    assert engine._coordinator_agent_id == "decision_coordinator"
