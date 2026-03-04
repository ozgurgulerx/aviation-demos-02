"""
Targeted regression tests for workflow progression safeguards.
"""

from __future__ import annotations

import asyncio
import pytest

from agent_framework import AgentExecutorResponse, AgentResponse, AgentResponseUpdate, AgentRunEvent, AgentRunUpdateEvent, ChatMessage, Content, ExecutorCompletedEvent, ExecutorInvokedEvent, WorkflowOutputEvent, WorkflowRunState, WorkflowStatusEvent
from agent_framework._workflows._handoff import HandoffSentEvent

from orchestrator.agent_registry import AgentSelectionResult, SCENARIO_AGENTS
from orchestrator.engine import OrchestratorEngine, _LoopCappedSignal
from orchestrator.trace_emitter import TraceEmitter
from orchestrator.workflows import (
    OrchestrationMode,
    WorkflowType,
    _SpecialistAggregator,
    create_coordinator_workflow,
    create_deterministic_coordinator_workflow,
    create_workflow,
)


def _agent(agent_id: str, name: str, category: str = "specialist") -> AgentSelectionResult:
    return AgentSelectionResult(
        agent_id=agent_id,
        agent_name=name,
        short_name=name,
        category=category,
        included=True,
        reason="test",
        conditions_evaluated=["test"],
        priority=1,
        icon="",
        color="#000000",
        data_sources=[],
    )


@pytest.mark.asyncio
async def test_executor_completed_uses_streaming_text_accum():
    """agent.completed should use accumulated streaming text when no AgentRunEvent fires."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-accum", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_x", "Specialist X")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    # Simulate: agent was invoked, produced streaming text, then completed
    # (no AgentRunEvent — only ExecutorCompletedEvent with None data)
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_x"))
    engine._streaming_text_accum["specialist_x"] = [
        "Detroit Metro (DTW) is the nearest suitable alternate. ",
        "Runway 21L is active with ILS approach available.",
    ]
    await engine._process_workflow_event(ExecutorCompletedEvent("specialist_x"))

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1
    assert completed[0]["message_count"] == 2
    assert "Detroit Metro" in completed[0]["summary"]


@pytest.mark.asyncio
async def test_agent_run_event_takes_priority_over_executor_completed():
    """When AgentRunEvent fires first, ExecutorCompletedEvent should NOT re-emit agent.completed."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-priority", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_y", "Specialist Y")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    # Simulate: invoked → AgentRunEvent (with real response) → ExecutorCompletedEvent (None data)
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_y"))

    response = AgentResponse(messages=[
        ChatMessage(role="assistant", text="DTW is 45 NM away with ILS 21L available and clear conditions."),
    ])
    await engine._process_workflow_event(AgentRunEvent("specialist_y", response))
    await engine._process_workflow_event(ExecutorCompletedEvent("specialist_y"))

    completed = [p for t, p in captured if t == "agent.completed"]
    # Only ONE agent.completed should be emitted (from AgentRunEvent), not two
    assert len(completed) == 1
    assert completed[0]["completionReason"] == "analysis_complete"
    assert completed[0]["message_count"] == 1
    assert "DTW" in completed[0]["summary"]


@pytest.mark.asyncio
async def test_executor_completed_fallback_when_no_agent_run_event():
    """When no AgentRunEvent fires, ExecutorCompletedEvent should use accumulated streaming text."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-fallback", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_z", "Specialist Z")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    # Simulate: invoked → streaming chunks accumulated → ExecutorCompletedEvent (no prior AgentRunEvent)
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_z"))
    engine._streaming_text_accum["specialist_z"] = [
        "Weather analysis complete. ",
        "METAR shows improving conditions at DTW. ",
        "Ceiling 2500ft, visibility 6SM.",
    ]
    await engine._process_workflow_event(ExecutorCompletedEvent("specialist_z"))

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1
    assert completed[0]["completionReason"] == "executor_completed"
    assert completed[0]["message_count"] == 3
    assert "Weather analysis complete" in completed[0]["summary"]
    assert "Specialist Z completed execution." not in completed[0]["summary"]


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
async def test_loop_guard_raises_runtime_error_in_sequential_mode():
    """In sequential mode, loop guard raises RuntimeError (not _LoopCappedSignal)."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-loop-guard",
        event_emitter=emit,
        enable_checkpointing=False,
        workflow_type=WorkflowType.SEQUENTIAL,
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
async def test_loop_guard_raises_loop_capped_signal_in_llm_directed_mode():
    """In LLM-directed mode with all specialists heard, raises _LoopCappedSignal."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-loop-cap",
        event_emitter=emit,
        enable_checkpointing=False,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        max_executor_invocations=1,
    )
    profile = _agent("specialist_a", "Specialist A", category="specialist")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}
    engine._max_executor_invocations_effective = 1

    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_a"))

    with pytest.raises(_LoopCappedSignal):
        await engine._process_workflow_event(ExecutorInvokedEvent("specialist_a"))

    status_events = [p for t, p in captured if t == "workflow.status" and p.get("status") == "loop_capped"]
    assert status_events, "workflow.status with loop_capped should be emitted"


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


@pytest.mark.usefixtures("_set_aoai_endpoint")
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
    # default_coordinator_turns = len(specialists) + 6 = 6 + 6 = 12
    assert getattr(coordinator_executor, "_autonomous_mode_turn_limit") == 12

    for specialist_id in specialist_ids:
        specialist_executor = workflow.executors[specialist_id]
        assert getattr(specialist_executor, "_handoff_targets") == {coordinator_id}
        assert getattr(specialist_executor, "_autonomous_mode_turn_limit") == 4


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_deterministic_workflow_has_parallel_specialists_and_coordinator():
    scenario = "diversion"
    scenario_config = SCENARIO_AGENTS[scenario]
    workflow = create_deterministic_coordinator_workflow(
        scenario=scenario,
        active_agent_ids=scenario_config["agents"] + [scenario_config["coordinator"]],
    )

    executor_ids = set(workflow.executors.keys())
    coordinator_id = scenario_config["coordinator"]
    # All specialists should be present as executors
    for specialist_id in scenario_config["agents"]:
        assert specialist_id in executor_ids, f"Specialist {specialist_id} missing from workflow executors"
    # Coordinator should be present under its real ID
    assert coordinator_id in executor_ids, f"Coordinator {coordinator_id} missing from workflow executors"
    # Aggregator should be present
    assert "specialist_aggregator" in executor_ids, "Specialist aggregator missing"

    # No handoff targets in deterministic mode
    for eid, executor in workflow.executors.items():
        assert getattr(executor, "_handoff_targets", set()) in (set(), None), (
            f"Executor {eid} has unexpected handoff targets"
        )


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_workflow_factory_routes_handoff_modes():
    problem = "Need a diversion plan to an alternate airport due to severe weather."

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

    # LLM-directed uses HandoffBuilder — coordinator has handoff targets
    scenario_config = SCENARIO_AGENTS["diversion"]
    coordinator_id = scenario_config["coordinator"]
    assert len(getattr(llm_directed_workflow.executors[coordinator_id], "_handoff_targets")) >= 1

    # Deterministic uses parallel WorkflowBuilder — no handoff targets
    assert getattr(deterministic_workflow.executors[coordinator_id], "_handoff_targets", set()) in (set(), None)


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
async def test_coordinator_control_json_does_not_emit_plan_or_answer():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-control-only-artifacts",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )

    await engine._emit_coordinator_artifacts('{"handoff_to":"situation_assessment"}')

    status_events = [payload for event_type, payload in captured if event_type == "workflow.status"]
    plan_events = [payload for event_type, payload in captured if event_type == "coordinator.plan"]
    assert status_events
    assert status_events[-1]["status"] == "coordinator_control_output_detected"
    assert status_events[-1]["coordinator_control_output_detected"] is True
    assert plan_events == []
    assert engine._latest_coordinator_artifacts.get("controlOnly") is True
    assert engine._latest_coordinator_artifacts.get("finalAnswer") == ""


def test_should_fail_when_coordinator_runs_without_specialists():
    engine = OrchestratorEngine(
        run_id="test-no-specialist-handoff",
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._coordinator_agent_id = "decision_coordinator"
    engine._agent_execution_counts["decision_coordinator"] = 1
    engine._latest_coordinator_response_text = '{"summary":"premature coordinator summary"}'

    should_fail = engine._should_fail_coordinator_no_specialist_handoff(
        artifacts={"summary": "premature coordinator summary"},
        agent_responses=[],
    )
    assert should_fail is True


def test_should_not_fail_when_specialist_participated():
    engine = OrchestratorEngine(
        run_id="test-has-specialist-handoff",
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._coordinator_agent_id = "decision_coordinator"
    engine._agent_execution_counts["decision_coordinator"] = 1
    engine._agent_execution_counts["specialist_a"] = 1
    engine._latest_coordinator_response_text = '{"summary":"coordinator summary"}'

    should_fail = engine._should_fail_coordinator_no_specialist_handoff(
        artifacts={"summary": "coordinator summary"},
        agent_responses=[{
            "agent": "specialist_a",
            "messages": 1,
            "result_summary": (
                '{"executive_summary":"Specialist identified 3 legal crew swaps",'
                '"evidence_points":["22% delay reduction option"],'
                '"recommended_actions":["Apply crew swap package A"],'
                '"risks":["Reserve FO depletion by T+120"],'
                '"confidence":0.79}'
            ),
        }],
    )
    assert should_fail is False


def test_parse_coordinator_artifacts_extracts_final_answer_from_json():
    engine = OrchestratorEngine(run_id="test-final-answer-json", enable_checkpointing=False)
    response = """Coordinator synthesis complete.
```json
{
  "criteria": ["delay_reduction", "crew_margin", "safety_score", "cost_impact", "passenger_impact"],
  "options": [
    {
      "optionId": "opt-1",
      "description": "Divert to DTW and rebalance connections",
      "rank": 1,
      "scores": {"delay_reduction": 82, "crew_margin": 75, "safety_score": 93, "cost_impact": 64, "passenger_impact": 79}
    }
  ],
  "selectedOptionId": "opt-1",
  "summary": "opt-1 minimizes knock-on delays while maintaining safety margins.",
  "finalAnswer": "Divert to DTW now, then recover ORD arrivals in two waves to minimize passenger disruption.",
  "timeline": [{"time": "T+0", "action": "Issue DTW diversion clearance", "agent": "diversion_advisor"}]
}
```
"""
    artifacts = engine._parse_coordinator_artifacts(response)
    assert artifacts["finalAnswer"].startswith("Divert to DTW now")
    assert artifacts["summary"].startswith("opt-1 minimizes")


def test_parse_coordinator_artifacts_ignores_generic_preamble_for_final_answer():
    engine = OrchestratorEngine(run_id="test-final-answer-boilerplate", enable_checkpointing=False)
    response = """Coordinator synthesis complete.
```json
{
  "criteria": ["delay_reduction", "crew_margin", "safety_score", "cost_impact", "passenger_impact"],
  "options": [
    {"optionId": "opt-1", "description": "Divert to DTW and rebalance connections", "rank": 1}
  ],
  "selectedOptionId": "opt-1",
  "summary": "opt-1 minimizes knock-on delays while maintaining safety margins.",
  "timeline": [{"time": "T+0", "action": "Issue DTW diversion clearance", "agent": "diversion_advisor"}]
}
```
"""
    artifacts = engine._parse_coordinator_artifacts(response)
    assert artifacts["summary"].startswith("opt-1 minimizes")
    assert artifacts["finalAnswer"] == artifacts["summary"]


def test_specialist_findings_contract_parses_from_json_block():
    engine = OrchestratorEngine(run_id="test-specialist-contract", enable_checkpointing=False)
    findings = engine._extract_specialist_findings_from_text(
        """```json
{
  "executive_summary": "ORD ground stop impacts 47 flights and 6800 passengers.",
  "evidence_points": ["47 flights delayed/cancelled", "3 runways closed"],
  "recommended_actions": ["Prioritize swap for bank-1 departures"],
  "risks": ["Crew legality erosion in T+90m window"],
  "confidence": 0.74
}
```"""
    )
    assert findings is not None
    assert findings["executive_summary"].startswith("ORD ground stop")
    assert findings["confidence"] == 0.74


def test_specialist_participation_requires_structured_findings():
    engine = OrchestratorEngine(
        run_id="test-structured-participation",
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._coordinator_agent_id = coordinator.agent_id

    unstructured = [{
        "agent": "specialist_a",
        "messages": 1,
        "result_summary": "General commentary without structured fields.",
    }]
    assert engine._has_specialist_participation(unstructured) is False

    structured = [{
        "agent": "specialist_a",
        "messages": 1,
        "result_summary": (
            '{"executive_summary":"Crew legality at risk",'
            '"evidence_points":["FO pairing at 11.5h duty"],'
            '"recommended_actions":["Swap reserve FO at LAX"],'
            '"risks":["FAR117 exceedance"],"confidence":0.68}'
        ),
    }]
    assert engine._has_specialist_participation(structured) is True
    assert "specialist_a" in engine._specialist_findings_map


def test_concrete_fallback_response_contains_required_fields():
    engine = OrchestratorEngine(run_id="test-concrete-fallback", enable_checkpointing=False)
    result = engine._build_concrete_fallback_result(reason="insufficient_specialist_analysis")
    assert result["status"] == "completed"
    assert result["isFallback"] is True
    assert result["fallbackMode"] == "sop_concrete"
    assert result["selectedOptionId"] == "opt-1"
    assert isinstance(result["timeline"], list) and result["timeline"]
    assert result["confidence"] in {"high", "medium", "low"}


def test_resolve_final_answer_prefers_explicit_output_answer():
    engine = OrchestratorEngine(run_id="test-answer-priority", enable_checkpointing=False)
    resolved = engine._resolve_final_answer(
        final_output={"answer": "Use Option 2 immediately and protect long-haul banks."},
        artifacts={
            "summary": "Operational summary",
            "finalAnswer": "This should not be selected",
        },
        agent_responses=[],
        fused_summary="Fused summary fallback",
    )
    assert resolved == "Use Option 2 immediately and protect long-haul banks."


def test_resolve_final_answer_synthesizes_from_artifacts_when_missing():
    engine = OrchestratorEngine(run_id="test-answer-fallback", enable_checkpointing=False)
    artifacts = {
        "summary": "Choose DTW diversion to preserve safety and maintain onward connectivity.",
        "selectedOptionId": "opt-2",
        "options": [
            {"optionId": "opt-1", "description": "Hold and reassess", "rank": 2},
            {"optionId": "opt-2", "description": "Divert to DTW with coordinated crew replan", "rank": 1},
        ],
        "timeline": [
            {"time": "T+0", "action": "Issue diversion clearance"},
            {"time": "T+15m", "action": "Rebook impacted connections"},
        ],
    }
    fused_summary = "Analysis complete. 4 specialists contributed."
    resolved = engine._resolve_final_answer(
        final_output={},
        artifacts=artifacts,
        agent_responses=[],
        fused_summary=fused_summary,
    )
    assert "Divert to DTW" in resolved
    assert resolved != fused_summary


def test_resolve_final_answer_ignores_control_payload_text():
    engine = OrchestratorEngine(run_id="test-answer-control-json", enable_checkpointing=False)
    resolved = engine._resolve_final_answer(
        final_output={"handoff_to": "situation_assessment"},
        artifacts={"summary": "", "finalAnswer": "", "controlOnly": True},
        agent_responses=[],
        fused_summary="Specialist evidence summary",
    )
    assert "handoff_to" not in resolved
    assert resolved


def test_resolve_final_answer_rejects_orchestration_preamble_fallback():
    engine = OrchestratorEngine(run_id="test-answer-noise-filter", enable_checkpointing=False)
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._coordinator_agent_id = "decision_coordinator"

    resolved = engine._resolve_final_answer(
        final_output={
            "answer": (
                "## Aviation Problem Analysis Task\nStreaming traces now. "
                "Final answer will appear when the run completes."
            ),
        },
        artifacts={
            "summary": "Analysis complete. 0 specialist agents contributed findings.",
            "finalAnswer": "",
        },
        agent_responses=[
            {
                "agent": "input-conversation",
                "messages": 1,
                "result_summary": "## Aviation Problem Analysis Task",
            },
            {
                "agent": "specialist_a",
                "messages": 0,
                "result_summary": "Analysis complete. 0 specialist agents contributed findings.",
            },
        ],
        fused_summary="Analysis complete. 0 specialist agents contributed findings.",
    )

    assert "aviation problem analysis task" not in resolved.lower()
    assert "sop-based" in resolved.lower()


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

    result = await engine._execute_workflow_with_events("test input")
    assert result["status"] == "completed"
    assert result["reason"] == "deterministic_execution_timeout"
    assert result["fallbackMode"] == "sop_concrete"

    status = [payload for event_type, payload in captured if event_type == "workflow.status"]
    assert status
    assert status[-1]["status"] == "sop_concrete_fallback"
    assert status[-1]["reason"] == "deterministic_execution_timeout"


@pytest.mark.asyncio
async def test_runtime_reason_code_passthrough(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-runtime-reason",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )

    async def _fail_with_reason(_input_message: str):
        raise RuntimeError("coordinator_no_specialist_handoff")

    monkeypatch.setattr(engine, "_stream_workflow", _fail_with_reason)

    result = await engine._execute_workflow_with_events("test input")
    assert result["status"] == "completed"
    assert result["reason"] == "coordinator_no_specialist_handoff"
    assert result["fallbackMode"] == "sop_concrete"
    assert "implement opt-1 immediately" in result["answer"].lower()

    status_events = [payload for event_type, payload in captured if event_type == "workflow.status"]
    assert status_events
    assert status_events[-1]["status"] == "sop_concrete_fallback"
    assert status_events[-1]["reason"] == "coordinator_no_specialist_handoff"


@pytest.mark.asyncio
async def test_runtime_reason_code_passthrough_for_insufficient_specialist_analysis(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-runtime-reason-insufficient-specialists",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.DETERMINISTIC,
        enable_checkpointing=False,
    )

    async def _fail_with_reason(_input_message: str):
        raise RuntimeError("insufficient_specialist_analysis")

    monkeypatch.setattr(engine, "_stream_workflow", _fail_with_reason)

    result = await engine._execute_workflow_with_events("test input")
    assert result["status"] == "completed"
    assert result["reason"] == "insufficient_specialist_analysis"
    assert result["fallbackMode"] == "sop_concrete"
    assert "implement opt-1 immediately" in result["answer"].lower()

    status_events = [payload for event_type, payload in captured if event_type == "workflow.status"]
    assert status_events
    assert status_events[-1]["status"] == "sop_concrete_fallback"
    assert status_events[-1]["reason"] == "insufficient_specialist_analysis"


class TestEstimateResultCount:
    """Tests for OrchestratorEngine._estimate_result_count."""

    def _engine(self):
        return OrchestratorEngine(run_id="test-erc", enable_checkpointing=False)

    def test_none_text_returns_zero(self):
        assert self._engine()._estimate_result_count("a", "db", None, 0) == 0

    def test_empty_text_returns_zero(self):
        assert self._engine()._estimate_result_count("a", "db", "", 0) == 0

    def test_whitespace_only_returns_zero(self):
        assert self._engine()._estimate_result_count("a", "db", "   \n  ", 0) == 0

    def test_short_text_returns_zero(self):
        assert self._engine()._estimate_result_count("a", "db", "Too short.", 0) == 0

    def test_single_paragraph_returns_one(self):
        text = "Detroit Metro (DTW) is the nearest suitable alternate airport with ILS approach available on runway 21L."
        assert self._engine()._estimate_result_count("a", "db", text, 0) == 1

    def test_multi_paragraph_returns_higher_count(self):
        text = (
            "Detroit Metro (DTW) is the nearest suitable alternate.\n\n"
            "Runway 21L is active with ILS approach available.\n\n"
            "Current weather is marginal VFR with improving trend."
        )
        result = self._engine()._estimate_result_count("a", "db", text, 0)
        assert result == 3

    def test_bulleted_list_counts_items(self):
        text = (
            "Alternate airport analysis results:\n"
            "- DTW: 45 NM, ILS 21L available\n"
            "- CLE: 120 NM, CAT III available\n"
            "- BUF: 95 NM, wind 15G25\n"
            "- PIT: 110 NM, clear conditions"
        )
        result = self._engine()._estimate_result_count("a", "db", text, 0)
        assert result >= 4

    def test_numbered_list_counts_items(self):
        text = (
            "Recovery plan steps identified:\n"
            "1. Dispatch tail swap for aircraft N12345\n"
            "2. Re-pair crew for flight 1042\n"
            "3. Issue NOTAM update for gate change\n"
            "4. Notify connecting passengers"
        )
        result = self._engine()._estimate_result_count("a", "db", text, 0)
        assert result >= 4

    def test_cap_at_25(self):
        paragraphs = "\n\n".join([f"Finding {i}: substantive text here." for i in range(40)])
        result = self._engine()._estimate_result_count("a", "db", paragraphs, 0)
        assert result == 25


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


@pytest.mark.asyncio
async def test_executor_completed_extracts_from_agent_executor_response():
    """agent.completed should extract text from AgentExecutorResponse in event.data."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-aer", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_y", "Specialist Y")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    # Simulate invocation
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_y"))

    # Create a real AgentExecutorResponse with content
    agent_resp = AgentResponse(messages=[
        ChatMessage(role="assistant", text="DTW is recommended. Runway 21L ILS available."),
    ])
    exec_resp = AgentExecutorResponse(
        executor_id="specialist_y",
        agent_response=agent_resp,
    )
    # Fire completion with data list containing the executor response
    completed_event = ExecutorCompletedEvent("specialist_y", [exec_resp])
    await engine._process_workflow_event(completed_event)

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1
    assert completed[0]["message_count"] >= 1
    assert "DTW" in completed[0]["summary"]


@pytest.mark.asyncio
async def test_stream_workflow_extracts_single_executor_response_for_specialist():
    class _FakeWorkflow:
        def __init__(self, events):
            self._events = events

        async def run_stream(self, _input):
            for event in self._events:
                yield event

    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-stream-single-specialist",
        event_emitter=emit,
        workflow_type=WorkflowType.SEQUENTIAL,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_single", "Specialist Single")
    engine.selected_agents = [specialist]
    engine._agent_lookup = {specialist.agent_id: specialist}

    specialist_resp = AgentExecutorResponse(
        executor_id=specialist.agent_id,
        agent_response=AgentResponse(messages=[
            ChatMessage(role="assistant", text="Crew swap plan ready with two reserve crews at ORD."),
        ]),
    )
    engine.workflow = _FakeWorkflow([
        ExecutorInvokedEvent(specialist.agent_id),
        ExecutorCompletedEvent(specialist.agent_id, specialist_resp),
        WorkflowOutputEvent({}, specialist.agent_id),
    ])

    result = await engine._stream_workflow("test")
    assert result["agent_responses"]
    assert result["agent_responses"][0]["agent"] == "specialist_single"
    assert result["agent_responses"][0]["messages"] >= 1
    assert "Crew swap plan ready" in result["agent_responses"][0]["result_summary"]
    assert "completed execution" not in result["summary"]


@pytest.mark.asyncio
async def test_stream_workflow_extracts_single_executor_response_for_coordinator():
    class _FakeWorkflow:
        def __init__(self, events):
            self._events = events

        async def run_stream(self, _input):
            for event in self._events:
                yield event

    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-stream-single-coordinator",
        event_emitter=emit,
        workflow_type=WorkflowType.SEQUENTIAL,
        enable_checkpointing=False,
    )
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [coordinator]
    engine._agent_lookup = {coordinator.agent_id: coordinator}
    engine._coordinator_agent_id = coordinator.agent_id

    coordinator_json = (
        '{"summary":"Divert to DTW and protect long-haul banks.",'
        '"finalAnswer":"Divert to DTW immediately and trigger reserve-crew swaps.",'
        '"options":[],'
        '"timeline":[],'
        '"selectedOptionId":""}'
    )
    coordinator_resp = AgentExecutorResponse(
        executor_id=coordinator.agent_id,
        agent_response=AgentResponse(messages=[
            ChatMessage(role="assistant", text=coordinator_json),
        ]),
    )
    engine.workflow = _FakeWorkflow([
        ExecutorInvokedEvent(coordinator.agent_id),
        ExecutorCompletedEvent(coordinator.agent_id, coordinator_resp),
        WorkflowOutputEvent({}, coordinator.agent_id),
    ])

    result = await engine._stream_workflow("test")
    assert result["answer"] == "Divert to DTW immediately and trigger reserve-crew swaps."
    assert result.get("finalAnswer") == "Divert to DTW immediately and trigger reserve-crew swaps."


@pytest.mark.asyncio
async def test_stream_workflow_phase_lock_all_required_allows_coordinator_synthesis():
    class _FakeWorkflow:
        def __init__(self, events):
            self._events = events

        async def run_stream(self, _input):
            for event in self._events:
                yield event

    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-phase-lock-all-required",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._agent_lookup = {
        specialist.agent_id: specialist,
        coordinator.agent_id: coordinator,
    }
    engine._coordinator_agent_id = coordinator.agent_id

    specialist_payload = (
        '{"executive_summary":"Crew legality at risk on two pairings.",'
        '"evidence_points":["2 pairings at 11.7h duty"],'
        '"recommended_actions":["Swap reserve FO at ORD"],'
        '"risks":["Reserve depletion by T+120"],'
        '"confidence":0.72}'
    )
    coordinator_payload = (
        '{"summary":"Apply reserve FO swap and rebalance rotations.",'
        '"finalAnswer":"Apply reserve FO swap now and rebalance crew rotations.",'
        '"criteria":["delay_reduction","crew_margin","safety_score","cost_impact","passenger_impact"],'
        '"options":[{"optionId":"opt-1","description":"Swap reserve FO at ORD","rank":1,'
        '"scores":{"delay_reduction":80,"crew_margin":78,"safety_score":90,"cost_impact":65,"passenger_impact":82}}],'
        '"timeline":[{"time":"T+0","action":"Swap reserve FO at ORD","agent":"crew_recovery"}],'
        '"selectedOptionId":"opt-1",'
        '"confidence":"high","assumptions":[],"evidenceCoverage":{"required":1,"contributed":1}}'
    )

    specialist_resp = AgentExecutorResponse(
        executor_id=specialist.agent_id,
        agent_response=AgentResponse(messages=[ChatMessage(role="assistant", text=specialist_payload)]),
    )
    coordinator_resp = AgentExecutorResponse(
        executor_id=coordinator.agent_id,
        agent_response=AgentResponse(messages=[ChatMessage(role="assistant", text=coordinator_payload)]),
    )

    engine.workflow = _FakeWorkflow([
        ExecutorInvokedEvent(specialist.agent_id),
        ExecutorCompletedEvent(specialist.agent_id, specialist_resp),
        ExecutorInvokedEvent(coordinator.agent_id),
        ExecutorCompletedEvent(coordinator.agent_id, coordinator_resp),
        WorkflowOutputEvent({}, coordinator.agent_id),
    ])

    result = await engine._stream_workflow("test")
    assert result["fallbackMode"] == "none"
    assert result["isFallback"] is False
    assert result["answer"] == "Apply reserve FO swap now and rebalance crew rotations."
    statuses = [p for t, p in captured if t == "workflow.status"]
    assert any(p.get("status") == "phase_lock_enabled" for p in statuses)


def test_concrete_fallback_result_aggregates_all_structured_findings():
    engine = OrchestratorEngine(run_id="test-fallback-aggregation", enable_checkpointing=False)
    engine._specialist_findings_map = {
        "specialist_a": {
            "executive_summary": "A summary",
            "evidence_points": ["First evidence point"],
            "recommended_actions": ["Action from specialist A"],
            "risks": ["First risk"],
            "confidence": 0.7,
        },
        "specialist_b": {
            "executive_summary": "B summary",
            "evidence_points": ["Second evidence point"],
            "recommended_actions": ["Action from specialist B"],
            "risks": ["Second risk"],
            "confidence": 0.8,
        },
    }

    result = engine._build_concrete_fallback_result(reason="insufficient_specialist_analysis")
    answer = result["answer"].lower()
    assert "first evidence point".lower() in answer
    assert "second evidence point".lower() in answer
    assert "first risk".lower() in answer
    assert "second risk".lower() in answer


@pytest.mark.asyncio
async def test_stream_workflow_fails_fast_on_control_only_superstep_streak():
    class _SuperStepStartedEvent:
        pass

    class _SuperStepCompletedEvent:
        pass

    class _FakeWorkflow:
        def __init__(self, events):
            self._events = events

        async def run_stream(self, _input):
            for event in self._events:
                yield event

    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-control-only-superstep-streak",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_streak", "Specialist Streak")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._agent_lookup = {
        specialist.agent_id: specialist,
        coordinator.agent_id: coordinator,
    }
    engine._coordinator_agent_id = coordinator.agent_id

    # 4 consecutive supersteps with only no-op invocation/completion should fail fast.
    events = []
    for _ in range(4):
        events.extend([
            _SuperStepStartedEvent(),
            ExecutorInvokedEvent("specialist_streak", {"should_respond": False}),
            ExecutorCompletedEvent("specialist_streak"),
            _SuperStepCompletedEvent(),
        ])
    engine.workflow = _FakeWorkflow(events)

    with pytest.raises(RuntimeError, match="insufficient_specialist_analysis"):
        await engine._stream_workflow("test")


@pytest.mark.asyncio
async def test_stream_workflow_fails_fast_on_noop_invocation_streak_without_supersteps():
    class _FakeWorkflow:
        def __init__(self, events):
            self._events = events

        async def run_stream(self, _input):
            for event in self._events:
                yield event

    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-noop-streak-no-supersteps",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_noop", "Specialist Noop")
    coordinator = _agent("decision_coordinator", "Decision Coordinator", category="coordinator")
    engine.selected_agents = [specialist, coordinator]
    engine._agent_lookup = {
        specialist.agent_id: specialist,
        coordinator.agent_id: coordinator,
    }
    engine._coordinator_agent_id = coordinator.agent_id

    events = []
    # Exceed max_noop_invocations_without_progress (24 for 1 specialist in llm-directed mode).
    for _ in range(25):
        events.extend([
            ExecutorInvokedEvent("specialist_noop", {"should_respond": False}),
            ExecutorCompletedEvent("specialist_noop"),
        ])
    engine.workflow = _FakeWorkflow(events)

    with pytest.raises(RuntimeError, match="insufficient_specialist_analysis"):
        await engine._stream_workflow("test")


@pytest.mark.asyncio
async def test_executor_completed_extracts_from_full_conversation():
    """agent.completed should extract text from full_conversation when agent_response is empty."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-fc", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_fc", "Specialist FC")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_fc"))

    # AgentExecutorResponse with empty agent_response but full_conversation
    agent_resp = AgentResponse(messages=[])
    exec_resp = AgentExecutorResponse(
        executor_id="specialist_fc",
        agent_response=agent_resp,
        full_conversation=[
            ChatMessage(role="user", text="Analyze weather at DTW"),
            ChatMessage(role="assistant", text="Ceiling 2500ft, visibility 6SM, improving trend."),
        ],
    )
    completed_event = ExecutorCompletedEvent("specialist_fc", [exec_resp])
    await engine._process_workflow_event(completed_event)

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1
    assert completed[0]["message_count"] >= 1
    assert "2500ft" in completed[0]["summary"]


@pytest.mark.asyncio
async def test_handoff_sent_event_captures_specialist_snapshot():
    """HandoffSentEvent should snapshot streaming text for specialist agents."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-handoff-snap", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_snap", "Specialist Snap")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}
    engine._coordinator_agent_id = "coordinator_main"

    # Simulate: specialist was invoked and accumulated streaming text
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_snap"))
    engine._streaming_text_accum["specialist_snap"] = [
        "Crew fatigue analysis shows 3 pairings at risk. ",
        "FDP limits will be exceeded within 2 hours for crew on flights 1042, 1055, 1078.",
    ]

    # Fire HandoffSentEvent — specialist hands back to coordinator
    await engine._process_workflow_event(HandoffSentEvent("specialist_snap", "coordinator_main"))

    # Snapshot should be captured
    assert "specialist_snap" in engine._handoff_specialist_snapshots
    snapshot = engine._handoff_specialist_snapshots["specialist_snap"]
    assert "Crew fatigue" in snapshot
    assert "FDP limits" in snapshot


@pytest.mark.asyncio
async def test_handoff_snapshot_not_captured_for_coordinator():
    """HandoffSentEvent from coordinator should NOT capture a snapshot."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-handoff-coord", event_emitter=emit, enable_checkpointing=False)
    engine._coordinator_agent_id = "coordinator_main"
    engine._streaming_text_accum["coordinator_main"] = ["Delegating to specialist."]

    await engine._process_workflow_event(HandoffSentEvent("coordinator_main", "specialist_a"))

    assert "coordinator_main" not in engine._handoff_specialist_snapshots


@pytest.mark.asyncio
async def test_handoff_snapshot_used_in_executor_completed_fallback():
    """ExecutorCompletedEvent should use handoff snapshot when event.data is None."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-snap-fallback", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_fb", "Specialist FB")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}
    engine._coordinator_agent_id = "coordinator_main"

    # Simulate: specialist was invoked
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_fb"))

    # Pre-populate handoff snapshot (as if HandoffSentEvent had fired)
    engine._handoff_specialist_snapshots["specialist_fb"] = (
        "Crew pairing analysis complete. 3 pairings at risk of FDP violation.\n\n"
        "Recommended: swap reserve crews on flights 1042 and 1055."
    )

    # Fire ExecutorCompletedEvent with None data (typical for handoff specialists)
    await engine._process_workflow_event(ExecutorCompletedEvent("specialist_fb"))

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1
    assert "Crew pairing analysis" in completed[0]["summary"]
    assert completed[0]["message_count"] >= 1


@pytest.mark.asyncio
async def test_reset_workflow_state_clears_handoff_snapshots():
    """_reset_workflow_state should clear handoff specialist snapshots."""
    engine = OrchestratorEngine(run_id="test-reset", enable_checkpointing=False)
    engine._handoff_specialist_snapshots["spec_a"] = "some analysis"
    engine._reset_workflow_state()
    assert len(engine._handoff_specialist_snapshots) == 0


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_problem_injected_into_specialist_instructions():
    """create_coordinator_workflow with problem= injects scenario context into specialist instructions."""
    problem = "Severe thunderstorm at ORD — 47 flights cancelled, 6800 passengers displaced."
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
        problem=problem,
    )

    specialist_ids = {
        "situation_assessment", "fleet_recovery", "crew_recovery",
        "network_impact", "weather_safety", "passenger_impact",
    }
    for specialist_id in specialist_ids:
        executor = workflow.executors[specialist_id]
        agent = executor._agent
        instructions = agent.default_options.get("instructions", "")
        assert "thunderstorm at ORD" in instructions, (
            f"{specialist_id} instructions missing problem context"
        )

    # Coordinator should also receive the problem context
    coord_executor = workflow.executors["recovery_coordinator"]
    coord_instructions = coord_executor._agent.default_options.get("instructions", "")
    assert "thunderstorm at ORD" in coord_instructions, (
        "Coordinator instructions missing problem context"
    )
    assert "Current Scenario" in coord_instructions


@pytest.mark.asyncio
async def test_streaming_accum_captures_function_result_content():
    """AgentRunUpdateEvent with function_result content should be accumulated."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-fn-result", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_fr", "Specialist FR")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}

    # Simulate invocation
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_fr"))

    # Create AgentRunUpdateEvent with function_result content (no text type)
    fn_result_content = Content.from_function_result(
        call_id="call_abc123",
        result="DTW: 45 NM, ILS 21L available, ceiling 2500ft, visibility 6SM",
    )
    update = AgentResponseUpdate(contents=[fn_result_content])
    await engine._process_workflow_event(AgentRunUpdateEvent("specialist_fr", update))

    # The function_result text should be accumulated
    chunks = engine._streaming_text_accum.get("specialist_fr", [])
    assert len(chunks) == 1
    assert "DTW" in chunks[0]
    assert "ILS 21L" in chunks[0]


@pytest.mark.asyncio
async def test_noop_invocation_does_not_count_as_real_execution():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-noop-counting",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    engine.selected_agents = [specialist]
    engine._agent_lookup = {specialist.agent_id: specialist}

    await engine._process_workflow_event(
        ExecutorInvokedEvent("specialist_a", {"should_respond": False}),
    )

    assert engine._agent_invocation_counts["specialist_a"] == 1
    assert engine._agent_execution_counts.get("specialist_a", 0) == 0
    assert engine._executor_invocations_total == 0
    assert engine._has_specialist_participation([]) is False

    invoked = [payload for event_type, payload in captured if event_type == "executor.invoked"]
    assert len(invoked) == 1
    assert invoked[0]["isNoOpInvocation"] is True
    assert invoked[0]["shouldRespond"] is False
    assert invoked[0]["realExecutionCount"] == 0


@pytest.mark.asyncio
async def test_loop_guard_ignores_noop_invocations_for_all_heard():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-loop-noop-guard",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        max_executor_invocations=1,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    engine.selected_agents = [specialist]
    engine._agent_lookup = {specialist.agent_id: specialist}
    engine._max_executor_invocations_effective = 1

    # no-op warm-up invocation should not count toward loop cap or specialist-heard coverage
    await engine._process_workflow_event(
        ExecutorInvokedEvent("specialist_a", {"should_respond": False}),
    )

    # first real invocation should still be accepted under cap
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_a"))

    # second real invocation crosses cap and now loop-caps gracefully
    with pytest.raises(_LoopCappedSignal):
        await engine._process_workflow_event(ExecutorInvokedEvent("specialist_a"))

    assert engine._executor_invocations_total == 2
    status_events = [p for t, p in captured if t == "workflow.status" and p.get("status") == "loop_capped"]
    assert status_events, "workflow.status with loop_capped should be emitted after real invocations exceed cap"


@pytest.mark.asyncio
async def test_noop_completion_does_not_emit_specialist_completion_or_evidence():
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-noop-completed",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
        enable_checkpointing=False,
    )
    specialist = _agent("specialist_a", "Specialist A", category="specialist")
    engine.selected_agents = [specialist]
    engine._agent_lookup = {specialist.agent_id: specialist}

    await engine._process_workflow_event(
        ExecutorInvokedEvent("specialist_a", {"should_respond": False}),
    )
    await engine._process_workflow_event(ExecutorCompletedEvent("specialist_a"))

    completed = [payload for event_type, payload in captured if event_type == "executor.completed"]
    agent_completed = [payload for event_type, payload in captured if event_type == "agent.completed"]

    assert len(completed) == 1
    assert completed[0]["status"] == "noop_completed"
    assert completed[0]["isNoOpInvocation"] is True
    assert completed[0]["shouldRespond"] is False
    assert agent_completed == []
    assert "specialist_a" not in engine._completed_agent_ids
    assert engine.evidence == []


def test_extract_response_text_reads_message_contents_function_result():
    engine = OrchestratorEngine(run_id="test-contents-function-result", enable_checkpointing=False)
    response = AgentResponse(messages=[
        ChatMessage(
            role="assistant",
            contents=[Content.from_function_result(call_id="call_1", result="DTW recommended with ILS 21L.")],
        )
    ])
    extracted = engine._extract_response_text(response)
    assert "DTW recommended" in extracted


@pytest.mark.asyncio
async def test_specialist_aggregator_includes_function_result_only_messages():
    class DummyContext:
        def __init__(self):
            self.calls: list[tuple[object, str | None]] = []

        async def send_message(self, message, target_id=None):
            self.calls.append((message, target_id))

    aggregator = _SpecialistAggregator(
        id="specialist_aggregator",
        coordinator_executor_id="decision_coordinator",
        specialist_ids=["maintenance_predictor"],
    )
    ctx = DummyContext()

    response = AgentResponse(
        messages=[
            ChatMessage(
                role="assistant",
                contents=[
                    Content.from_function_result(
                        call_id="call_1",
                        result={
                            "trend": "rising",
                            "repeat_tails": ["N738AA", "N739AA", "N741AA"],
                            "recommendation": "escalate borescope inspection cadence",
                        },
                    )
                ],
            )
        ]
    )
    results = [
        AgentExecutorResponse(
            executor_id="maintenance_predictor",
            agent_response=response,
        )
    ]

    await aggregator.aggregate(results, ctx)

    assert len(ctx.calls) == 1
    message, target_id = ctx.calls[0]
    assert target_id == "decision_coordinator"
    assert isinstance(message, list) and len(message) == 1
    outbound = message[0]
    assert "No findings returned" not in (outbound.text or "")
    assert "N738AA" in (outbound.text or "")
    assert "borescope inspection cadence" in (outbound.text or "")


@pytest.mark.asyncio
async def test_handoff_snapshot_uses_accumulated_tool_results():
    """HandoffSentEvent should capture snapshot from function_result content accumulated via streaming."""
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(run_id="test-snap-tool", event_emitter=emit, enable_checkpointing=False)
    profile = _agent("specialist_tool", "Specialist Tool")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}
    engine._coordinator_agent_id = "coordinator_main"

    # Simulate: invocation
    await engine._process_workflow_event(ExecutorInvokedEvent("specialist_tool"))

    # Simulate: streaming with function_result content
    fn_result = Content.from_function_result(
        call_id="call_tool1",
        result="Crew pairing CP-1042 exceeds FDP by 45 minutes. Reserve crew available at base DTW.",
    )
    update = AgentResponseUpdate(contents=[fn_result])
    await engine._process_workflow_event(AgentRunUpdateEvent("specialist_tool", update))

    # Simulate: HandoffSentEvent — specialist hands back to coordinator
    await engine._process_workflow_event(HandoffSentEvent("specialist_tool", "coordinator_main"))

    # Snapshot should be captured from the accumulated function_result content
    assert "specialist_tool" in engine._handoff_specialist_snapshots
    snapshot = engine._handoff_specialist_snapshots["specialist_tool"]
    assert "Crew pairing CP-1042" in snapshot
    assert "FDP" in snapshot


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_coordinator_instructions_include_json_schema():
    """LLM-directed coordinator instructions should include a valid JSON output schema."""
    workflow = create_coordinator_workflow(
        scenario="hub_disruption",
        active_agent_ids=[
            "situation_assessment",
            "fleet_recovery",
            "recovery_coordinator",
        ],
    )
    coordinator_executor = workflow.executors["recovery_coordinator"]
    instructions = coordinator_executor._agent.default_options.get("instructions", "")
    assert "selectedOptionId" in instructions
    assert "timeline" in instructions
    assert "criteria" in instructions
    # Braces should be single (valid JSON), not double-escaped
    assert '{"time":' in instructions.replace(" ", "") or '"time"' in instructions
    assert "{{" not in instructions, (
        "Coordinator instructions contain double-braces — JSON schema is malformed"
    )
    assert "Never output `{\"handoff_to\":\"...\"}`" in instructions


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_problem_passed_through_create_workflow():
    """create_workflow(problem=...) should propagate into specialist instructions."""
    problem = "Ground stop at JFK due to low visibility — 30 flights held."
    workflow = create_workflow(
        workflow_type=WorkflowType.HANDOFF,
        problem=problem,
        orchestration_mode=OrchestrationMode.LLM_DIRECTED,
    )
    # Find any specialist executor and check for problem text
    found = False
    for eid, executor in workflow.executors.items():
        agent = getattr(executor, "_agent", None)
        if agent and "JFK" in (agent.default_options.get("instructions") or ""):
            found = True
            break
    assert found, "Problem text not found in any specialist instructions"


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_coordinator_turn_limits_with_problem():
    """Turn limits should remain correct even when problem is injected."""
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
        problem="Test problem for turn limit validation.",
    )
    coordinator_executor = workflow.executors["recovery_coordinator"]
    # 6 specialists + 6 = 12
    assert getattr(coordinator_executor, "_autonomous_mode_turn_limit") == 12


class TestScenarioAwareFallbacks:
    """Tests for scenario-aware fallback helpers and their integration in tools."""

    def test_disruption_fallback_basic(self):
        from agents.tools.domain_knowledge import contextualize_disruption_fallback
        result = contextualize_disruption_fallback(["ORD"], time_window_hours=6)
        assert result["hub_airport"] == "ORD"
        assert result["time_window_hours"] == 6
        assert result["recovery_category"] == "minor"

    def test_disruption_fallback_major(self):
        from agents.tools.domain_knowledge import contextualize_disruption_fallback
        result = contextualize_disruption_fallback(
            ["ORD"], cancelled_flights=47, affected_pax=6800,
        )
        assert result["recovery_category"] == "major"
        assert result["estimated_cascade_flights"] == round(47 * 1.8)
        assert result["connecting_pax_at_risk"] == round(6800 * 0.50)

    def test_network_fallback_basic(self):
        from agents.tools.domain_knowledge import contextualize_network_fallback
        result = contextualize_network_fallback("ORD", delay_minutes=90, cascade_hops=3)
        assert result["origin_airport"] == "ORD"
        assert result["reactionary_delay_minutes"] == 72
        assert result["recovery_category"] == "moderate"

    def test_network_fallback_major(self):
        from agents.tools.domain_knowledge import contextualize_network_fallback
        result = contextualize_network_fallback("ORD", delay_minutes=180, cascade_hops=2)
        assert result["recovery_category"] == "major"

    def test_passenger_fallback_basic(self):
        from agents.tools.domain_knowledge import contextualize_passenger_fallback
        result = contextualize_passenger_fallback("ORD", cancelled_flights=47)
        assert result["hub_airport"] == "ORD"
        assert result["displaced_pax"] == 47 * 150
        assert result["rebooking_pressure"] == "extreme"

    def test_passenger_fallback_low(self):
        from agents.tools.domain_knowledge import contextualize_passenger_fallback
        result = contextualize_passenger_fallback("SFO", cancelled_flights=2)
        assert result["rebooking_pressure"] == "low"

    @pytest.mark.asyncio
    async def test_map_disruption_scope_returns_scenario_estimates(self):
        from agents.tools.situation_tools import map_disruption_scope
        result = await map_disruption_scope(["ORD"], time_window_hours=6)
        assert result["status"] == "no_data_fallback"
        assert "scenario_estimates" in result
        assert result["scenario_estimates"]["hub_airport"] == "ORD"

    @pytest.mark.asyncio
    async def test_simulate_delay_propagation_returns_scenario_estimates(self):
        from agents.tools.network_tools import simulate_delay_propagation
        result = await simulate_delay_propagation("ORD", delay_minutes=120, cascade_hops=3)
        assert result["status"] == "no_data_fallback"
        assert "scenario_estimates" in result
        assert result["scenario_estimates"]["origin_airport"] == "ORD"

    @pytest.mark.asyncio
    async def test_estimate_rebooking_load_returns_scenario_estimates(self):
        from agents.tools.passenger_tools import estimate_rebooking_load
        result = await estimate_rebooking_load("ORD", cancelled_flights=47)
        assert result["status"] == "no_data_fallback"
        assert "scenario_estimates" in result
        assert result["scenario_estimates"]["hub_airport"] == "ORD"
        assert result["scenario_estimates"]["displaced_pax"] == 47 * 150

    @pytest.mark.asyncio
    async def test_query_crew_availability_returns_scenario_estimates(self):
        from agents.tools.crew_tools import query_crew_availability
        result = await query_crew_availability("ORD", role="captain")
        assert result["status"] == "no_data_fallback"
        assert "scenario_estimates" in result
        assert result["scenario_estimates"]["base_airport"] == "ORD"
        assert result["scenario_estimates"]["role_queried"] == "captain"

    @pytest.mark.asyncio
    async def test_find_available_tails_returns_scenario_estimates(self):
        from agents.tools.fleet_tools import find_available_tails
        result = await find_available_tails("B737", "ORD")
        assert result["status"] == "no_data_fallback"
        assert "scenario_estimates" in result
        assert result["scenario_estimates"]["base_airport"] == "ORD"
        assert result["scenario_estimates"]["spare_ratio"] == "5-8%"

    @pytest.mark.asyncio
    async def test_check_sigmets_returns_scenario_estimates(self):
        from agents.tools.weather_safety_tools import check_sigmets_pireps
        result = await check_sigmets_pireps(["ORD", "MDW"])
        assert result["status"] == "no_data_fallback"
        assert "scenario_estimates" in result
        assert result["scenario_estimates"]["airports_assessed"] == ["ORD", "MDW"]


@pytest.mark.usefixtures("_set_aoai_endpoint")
def test_specialist_turn_limits_are_four():
    """Specialist default turn limits should be 4 (not 2) to allow text generation before handoff."""
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

    specialist_ids = {
        "situation_assessment", "fleet_recovery", "crew_recovery",
        "network_impact", "weather_safety", "passenger_impact",
    }
    for specialist_id in specialist_ids:
        specialist_executor = workflow.executors[specialist_id]
        assert getattr(specialist_executor, "_autonomous_mode_turn_limit") == 4, (
            f"{specialist_id} should have turn limit 4, got "
            f"{getattr(specialist_executor, '_autonomous_mode_turn_limit')}"
        )
