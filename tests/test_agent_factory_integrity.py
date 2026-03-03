"""Tests verifying agent factory registry integrity."""

from __future__ import annotations

import pytest

from orchestrator.agent_registry import AGENT_REGISTRY, get_agent_by_id
from agents import agent_factories


@pytest.fixture(autouse=True)
def _ensure_aoai(_set_aoai_endpoint):
    """All tests in this module need Azure OpenAI env patched."""
    pass


# ---------- Registry <-> Factory coverage ----------

def test_every_registry_agent_has_factory():
    """Every agent in AGENT_REGISTRY must have a corresponding factory."""
    missing = []
    for agent_def in AGENT_REGISTRY:
        if agent_def.id not in agent_factories:
            missing.append(agent_def.id)
    assert not missing, f"Agents missing from agent_factories: {missing}"


def _get_agent_tools(agent):
    """Extract tool list from a ChatAgent's default_options."""
    return agent.default_options.get("tools") or []


def test_every_factory_produces_a_chat_agent():
    """Every factory must return an object (ChatAgent) without raising."""
    for agent_id, factory in agent_factories.items():
        try:
            agent = factory(name=f"test_{agent_id}")
        except Exception as e:
            pytest.fail(f"Factory for {agent_id} raised: {e}")
        assert agent is not None, f"Factory for {agent_id} returned None"
        assert hasattr(agent, "name") or hasattr(agent, "id"), (
            f"Factory for {agent_id} returned object without name or id"
        )


# ---------- Coordinator tools ----------

COORDINATOR_TOOL_NAMES = {"score_recovery_option", "rank_options", "generate_plan"}
COORDINATOR_IDS = [a.id for a in AGENT_REGISTRY if a.category == "coordinator"]


@pytest.mark.parametrize("coordinator_id", COORDINATOR_IDS)
def test_coordinators_have_coordinator_tools(coordinator_id):
    """Coordinator agents must have scoring/ranking/planning tools."""
    factory = agent_factories.get(coordinator_id)
    assert factory is not None, f"No factory for coordinator {coordinator_id}"
    agent = factory(name=f"test_{coordinator_id}")
    tools = _get_agent_tools(agent)
    tool_names = {t.name if hasattr(t, "name") else str(t) for t in tools}
    missing = COORDINATOR_TOOL_NAMES - tool_names
    assert not missing, f"Coordinator {coordinator_id} missing tools: {missing}"


# ---------- Placeholder mismatch ----------

PLACEHOLDER_IDS = [a.id for a in AGENT_REGISTRY if a.category == "placeholder"]


@pytest.mark.parametrize("placeholder_id", PLACEHOLDER_IDS)
def test_placeholder_agents_are_marked_phase2(placeholder_id):
    """Placeholder agents must have phase >= 2 in the registry."""
    agent_def = get_agent_by_id(placeholder_id)
    assert agent_def is not None
    assert agent_def.phase >= 2, (
        f"Placeholder {placeholder_id} has phase={agent_def.phase}; expected >= 2"
    )


# ---------- Non-placeholder specialists ----------

NON_PLACEHOLDER_SPECIALIST_IDS = [
    a.id for a in AGENT_REGISTRY
    if a.category == "specialist" and a.phase == 1
]


@pytest.mark.parametrize("specialist_id", NON_PLACEHOLDER_SPECIALIST_IDS)
def test_non_placeholder_specialists_have_tools(specialist_id):
    """Phase-1 specialists must have at least one domain-specific tool."""
    factory = agent_factories.get(specialist_id)
    assert factory is not None, f"No factory for specialist {specialist_id}"
    agent = factory(name=f"test_{specialist_id}")
    tools = _get_agent_tools(agent)
    assert len(tools) >= 1, (
        f"Specialist {specialist_id} has no tools"
    )
