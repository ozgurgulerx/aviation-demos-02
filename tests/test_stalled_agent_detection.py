"""Tests for stalled agent detection across orchestration modes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock

from orchestrator.agent_registry import AgentSelectionResult
from orchestrator.engine import OrchestratorEngine
from orchestrator.workflows import OrchestrationMode, WorkflowType


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


def _make_engine(orchestration_mode: str) -> tuple[OrchestratorEngine, list]:
    captured: list[tuple[str, dict]] = []

    async def emit(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="test-stall",
        event_emitter=emit,
        workflow_type=WorkflowType.HANDOFF,
        orchestration_mode=orchestration_mode,
        enable_checkpointing=False,
    )
    profile = _agent("agent_a", "Agent A")
    engine.selected_agents = [profile]
    engine._agent_lookup = {profile.agent_id: profile}
    return engine, captured


@pytest.mark.asyncio
async def test_stalled_detection_fires_in_llm_directed_mode():
    """Stalled agent detection must work in LLM-directed mode (not just deterministic)."""
    engine, captured = _make_engine(OrchestrationMode.LLM_DIRECTED)
    engine._llm_directed_stream_timeout_seconds = 10

    stale_time = datetime.now(timezone.utc) - timedelta(seconds=15)
    engine._active_agent_ids.add("agent_a")
    engine._agent_stream_last_update_at["agent_a"] = stale_time
    engine._agent_execution_counts["agent_a"] = 1

    await engine._check_stalled_streaming_agents()

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1, "Stalled agent should be synthetically completed in LLM-directed mode"


@pytest.mark.asyncio
async def test_stalled_detection_fires_in_deterministic_mode():
    """Regression: stalled detection still works in deterministic mode."""
    engine, captured = _make_engine(OrchestrationMode.DETERMINISTIC)
    engine._deterministic_stream_timeout_seconds = 10

    stale_time = datetime.now(timezone.utc) - timedelta(seconds=15)
    engine._active_agent_ids.add("agent_a")
    engine._agent_stream_last_update_at["agent_a"] = stale_time
    engine._agent_execution_counts["agent_a"] = 1

    await engine._check_stalled_streaming_agents()

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1, "Stalled agent should be synthetically completed in deterministic mode"


@pytest.mark.asyncio
async def test_no_false_positive_when_agent_recently_active():
    """Agent that was recently active should NOT be considered stalled."""
    engine, captured = _make_engine(OrchestrationMode.LLM_DIRECTED)
    engine._llm_directed_stream_timeout_seconds = 120

    recent_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    engine._active_agent_ids.add("agent_a")
    engine._agent_stream_last_update_at["agent_a"] = recent_time
    engine._agent_execution_counts["agent_a"] = 1

    await engine._check_stalled_streaming_agents()

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 0, "Recently active agent should not be synthetically completed"


@pytest.mark.asyncio
async def test_no_action_when_no_active_agents():
    """No crash or action when there are no active agents."""
    engine, captured = _make_engine(OrchestrationMode.LLM_DIRECTED)
    assert len(engine._active_agent_ids) == 0
    await engine._check_stalled_streaming_agents()
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_llm_directed_uses_shorter_timeout():
    """LLM-directed mode uses its own (shorter) timeout, not deterministic timeout."""
    engine, captured = _make_engine(OrchestrationMode.LLM_DIRECTED)
    engine._llm_directed_stream_timeout_seconds = 60
    engine._deterministic_stream_timeout_seconds = 180

    # 90 seconds: past LLM-directed timeout but not deterministic
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=90)
    engine._active_agent_ids.add("agent_a")
    engine._agent_stream_last_update_at["agent_a"] = stale_time
    engine._agent_execution_counts["agent_a"] = 1

    await engine._check_stalled_streaming_agents()

    completed = [p for t, p in captured if t == "agent.completed"]
    assert len(completed) == 1, "Should fire at LLM-directed timeout (60s), not deterministic (180s)"
