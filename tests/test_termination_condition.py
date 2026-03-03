"""Tests for handoff workflow termination condition."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.workflows import create_coordinator_workflow


def _msg(text: str):
    """Create a mock message object with a text attribute."""
    return SimpleNamespace(text=text)


@pytest.fixture
def termination_fn(_set_aoai_endpoint):
    """Build a coordinator workflow and extract its should_terminate function."""
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
    # Termination condition is stored on each HandoffAgentExecutor
    coordinator_executor = workflow.executors["recovery_coordinator"]
    return coordinator_executor._termination_condition


# ---------- Keyword variant tests ----------

@pytest.mark.parametrize("rec_word,time_word", [
    ("recommend", "timeline"),
    ("final", "implementation"),
    ("suggest", "timeline"),
    ("propose", "summary"),
    ("conclusion", "plan"),
    ("decision", "next steps"),
    ("advise", "action items"),
    ("our plan", "schedule"),
])
def test_terminates_on_keyword_variants(termination_fn, rec_word, time_word):
    """Should terminate when a recommendation keyword + timeline keyword both appear."""
    conversation = [
        _msg("Specialist A reporting in."),
        _msg("Specialist B reporting in."),
        _msg("Specialist C reporting in."),
        _msg("Specialist D reporting in."),
        _msg(f"Based on analysis, I {rec_word} option A. Here is the {time_word}."),
    ]
    assert termination_fn(conversation) is True


def test_does_not_terminate_with_only_recommendation_keyword(termination_fn):
    """Should NOT terminate if only a recommendation keyword is present."""
    conversation = [
        _msg("Starting analysis."),
        _msg("Data gathered."),
        _msg("Processing."),
        _msg("Analyzing."),
        _msg("I recommend option A."),
    ]
    assert termination_fn(conversation) is False


def test_does_not_terminate_with_only_timeline_keyword(termination_fn):
    """Should NOT terminate if only a timeline keyword is present."""
    conversation = [
        _msg("Starting analysis."),
        _msg("Data gathered."),
        _msg("Processing."),
        _msg("Analyzing."),
        _msg("Here is the implementation timeline."),
    ]
    assert termination_fn(conversation) is False


# ---------- Tool signal tests ----------

@pytest.mark.parametrize("tool_name", [
    "generate_plan",
    "rank_options",
    "score_recovery_option",
])
def test_terminates_on_final_tool_signals(termination_fn, tool_name):
    """Should terminate when a coordinator tool name appears in recent messages."""
    conversation = [
        _msg("Agent starting."),
        _msg("Analysis done."),
        _msg("Processing options."),
        _msg("Running scoring."),
        _msg(f"Calling {tool_name} to finalize."),
    ]
    assert termination_fn(conversation) is True


# ---------- Safety valve tests ----------

def test_safety_valve_with_6_specialists(termination_fn):
    """Safety valve should fire at n_specialists * 2 + 4 = 16 messages for 6 specialists."""
    # 17 messages should trigger safety valve (> 16)
    conversation = [_msg(f"Message {i}") for i in range(17)]
    assert termination_fn(conversation) is True


def test_no_premature_termination_under_safety_valve(termination_fn):
    """Should not fire safety valve under threshold."""
    # 15 messages should NOT trigger safety valve (not > 16)
    conversation = [_msg(f"Message {i}") for i in range(15)]
    assert termination_fn(conversation) is False


# ---------- Edge cases ----------

def test_no_termination_on_very_short_conversation(termination_fn):
    """Should never terminate conversations shorter than 4 messages."""
    conversation = [_msg("I recommend this. Timeline: now.")]
    assert termination_fn(conversation) is False

    conversation = [_msg("x"), _msg("y"), _msg("I recommend. Timeline.")]
    assert termination_fn(conversation) is False
