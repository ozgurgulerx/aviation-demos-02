"""
End-to-end tests for the 4 frontend scenario use cases.

Drives OrchestratorEngine directly with real Azure OpenAI and mocked retriever.
Each test runs a full scenario through the LLM-directed workflow where gpt-5-mini
dynamically selects which agents to recruit and the coordinator delegates to
specialists via HandoffBuilder tool calls.

Usage:
    # All E2E tests (needs AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY)
    pytest tests/test_e2e_scenarios.py -v -s

    # Single scenario
    pytest tests/test_e2e_scenarios.py::test_scenario_completes[hub_disruption] -v -s

    # Exclude from regular CI
    pytest tests/ -v -m "not e2e"
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv

from e2e_helpers import (
    SCENARIOS,
    EventCollector,
    validate_agent_activations,
    validate_coordinator_invoked,
    validate_coordinator_output,
    validate_llm_selection_trace,
    validate_no_run_failed,
    validate_run_completed,
    validate_scenario_detected,
    validate_specialists_invoked,
)

# Load .env from project root so Azure creds are available
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ---------------------------------------------------------------------------
# Skip entire module when Azure credentials are not configured
# ---------------------------------------------------------------------------
_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
_HAS_CREDS = bool(_ENDPOINT) and bool(_API_KEY) and _API_KEY != "your_api_key_here"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not _HAS_CREDS, reason="Azure OpenAI credentials not set"),
]

# Per-test timeout (seconds) — generous to account for LLM latency
E2E_TIMEOUT = 480


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _patch_aoai_module_vars(monkeypatch):
    """Ensure the agents.client module-level vars match env for this process."""
    import agents.client as client_mod
    monkeypatch.setattr(client_mod, "AZURE_OPENAI_ENDPOINT", _ENDPOINT)
    monkeypatch.setattr(client_mod, "AZURE_OPENAI_KEY", _API_KEY)
    monkeypatch.setenv("AZURE_OPENAI_AUTH_MODE", "api-key")


@pytest.fixture
def event_collector() -> EventCollector:
    return EventCollector()


# ---------------------------------------------------------------------------
# Helper to run a scenario through the engine
# ---------------------------------------------------------------------------

async def _run_scenario(
    scenario_key: str,
    event_collector: EventCollector,
):
    """Create engine, run scenario prompt, return (engine, result)."""
    from orchestrator.engine import OrchestratorEngine

    scenario = SCENARIOS[scenario_key]
    engine = OrchestratorEngine(
        run_id=f"e2e-{scenario_key}-{uuid.uuid4().hex[:8]}",
        event_emitter=event_collector,
        workflow_type="handoff",
        orchestration_mode="llm_directed",
        max_executor_invocations=200,
        enable_checkpointing=False,
    )

    try:
        result = await asyncio.wait_for(
            engine.run(scenario["prompt"]),
            timeout=E2E_TIMEOUT,
        )
    except asyncio.TimeoutError:
        pytest.fail(
            f"Scenario '{scenario_key}' timed out after {E2E_TIMEOUT}s\n"
            f"Timeline:\n{event_collector.dump_timeline()}"
        )
    except Exception as exc:
        pytest.fail(
            f"Scenario '{scenario_key}' raised {type(exc).__name__}: {exc}\n"
            f"Timeline:\n{event_collector.dump_timeline()}"
        )

    return engine, result


# ---------------------------------------------------------------------------
# Parametrized core test — runs all 4 scenarios
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_key", list(SCENARIOS.keys()))
async def test_scenario_completes(
    scenario_key: str,
    wire_retriever,
    _patch_aoai_module_vars,
    event_collector: EventCollector,
):
    """Run a full scenario through OrchestratorEngine and validate the event stream."""
    scenario = SCENARIOS[scenario_key]
    expected_agents = scenario["expected_agents"]
    expected_coordinator = scenario["expected_coordinator"]
    expected_scenario_id = scenario["scenario_id"]

    engine, result = await _run_scenario(scenario_key, event_collector)

    # -- Hard assertions (must always pass) ----------------------------------

    # 1. Correct scenario detected
    validate_scenario_detected(engine, expected_scenario_id, event_collector)

    # 2. Correct agents activated (coordinator + at least N-1 specialists)
    validate_agent_activations(event_collector, expected_agents, expected_coordinator)

    # 3. Correct coordinator selected
    assert engine._coordinator_agent_id == expected_coordinator, (
        f"Expected coordinator '{expected_coordinator}', "
        f"got '{engine._coordinator_agent_id}'\n"
        f"Timeline:\n{event_collector.dump_timeline()}"
    )

    # 4. No RUN_FAILED
    validate_no_run_failed(event_collector)

    # 5. RUN_COMPLETED emitted
    validate_run_completed(event_collector)

    # 6. Result is non-empty
    assert result is not None, (
        f"engine.run() returned None\n"
        f"Timeline:\n{event_collector.dump_timeline()}"
    )

    # 7. LLM agent-selection trace event emitted
    validate_llm_selection_trace(event_collector)

    # 8. Coordinator invoked (must always run in LLM-directed mode)
    validate_coordinator_invoked(event_collector, expected_coordinator)

    # 9. At least some specialists invoked via handoff
    validate_specialists_invoked(event_collector, expected_agents)

    # 10. Coordinator completed (warn if no structured artifacts)
    validate_coordinator_output(event_collector)


# ---------------------------------------------------------------------------
# Scenario-specific tests
# ---------------------------------------------------------------------------

async def test_hub_disruption_uses_recovery_coordinator(
    wire_retriever,
    _patch_aoai_module_vars,
    event_collector: EventCollector,
):
    """Hub disruption must use recovery_coordinator, not decision_coordinator."""
    engine, _ = await _run_scenario("hub_disruption", event_collector)

    assert engine._coordinator_agent_id == "recovery_coordinator", (
        f"Expected recovery_coordinator, got {engine._coordinator_agent_id}\n"
        f"Timeline:\n{event_collector.dump_timeline()}"
    )
    assert engine._coordinator_agent_id != "decision_coordinator"


async def test_diversion_has_five_specialists(
    wire_retriever,
    _patch_aoai_module_vars,
    event_collector: EventCollector,
):
    """Diversion scenario should activate exactly 5 specialists."""
    engine, _ = await _run_scenario("diversion", event_collector)

    activated = event_collector.get_activated_agent_ids()
    specialists = [a for a in activated if a != "decision_coordinator"]
    assert len(specialists) == 5, (
        f"Expected 5 specialists, got {len(specialists)}: {specialists}\n"
        f"Timeline:\n{event_collector.dump_timeline()}"
    )


async def test_crew_fatigue_selects_fatigue_agents(
    wire_retriever,
    _patch_aoai_module_vars,
    event_collector: EventCollector,
):
    """Crew fatigue scenario must include crew_fatigue_assessor and crew_recovery."""
    engine, _ = await _run_scenario("crew_fatigue", event_collector)

    activated = set(event_collector.get_activated_agent_ids())
    for required in ("crew_fatigue_assessor", "crew_recovery"):
        assert required in activated, (
            f"'{required}' not activated for crew_fatigue scenario\n"
            f"Activated: {sorted(activated)}\n"
            f"Timeline:\n{event_collector.dump_timeline()}"
        )
    assert engine.scenario == "crew_fatigue"
