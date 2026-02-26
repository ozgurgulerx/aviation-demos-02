"""
Tests for agent creation and agent registry.
"""

import pytest
from orchestrator.agent_registry import (
    AGENT_REGISTRY,
    get_agent_registry,
    get_agent_by_id,
    select_agents_for_problem,
    AgentDefinition,
)


class TestAgentRegistry:
    def test_registry_has_three_agents(self):
        assert len(AGENT_REGISTRY) == 3

    def test_get_agent_registry_returns_copy(self):
        registry = get_agent_registry()
        assert len(registry) == 3

    def test_agent_ids(self):
        ids = [a.id for a in AGENT_REGISTRY]
        assert "flight_analyst" in ids
        assert "operations_advisor" in ids
        assert "safety_inspector" in ids

    def test_agent_categories(self):
        for agent in AGENT_REGISTRY:
            assert agent.category == "core"

    def test_agent_priorities_ordered(self):
        priorities = [a.priority for a in AGENT_REGISTRY]
        assert priorities == sorted(priorities)

    def test_get_agent_by_id_found(self):
        agent = get_agent_by_id("flight_analyst")
        assert agent is not None
        assert agent.name == "Flight Analyst Agent"
        assert agent.short_name == "Flight"

    def test_get_agent_by_id_not_found(self):
        agent = get_agent_by_id("nonexistent")
        assert agent is None


class TestAgentSelection:
    def test_select_all_agents_for_generic_problem(self):
        included, excluded = select_agents_for_problem("Flight delayed due to weather")
        assert len(included) == 3
        assert len(excluded) == 0

    def test_included_agents_sorted_by_priority(self):
        included, _ = select_agents_for_problem("Test problem")
        priorities = [a.priority for a in included]
        assert priorities == sorted(priorities)

    def test_selection_result_fields(self):
        included, _ = select_agents_for_problem("Test")
        for result in included:
            assert result.agent_id
            assert result.agent_name
            assert result.short_name
            assert result.category == "core"
            assert result.included is True
            assert result.reason
            assert len(result.conditions_evaluated) > 0

    def test_empty_problem_still_selects(self):
        included, excluded = select_agents_for_problem("")
        assert len(included) == 3


class TestAgentDefinition:
    def test_agent_definition_model(self):
        agent = AgentDefinition(
            id="test_agent",
            name="Test Agent",
            short_name="Test",
            category="conditional",
            description="A test agent",
            default_include=False,
            priority=99,
        )
        assert agent.id == "test_agent"
        assert agent.default_include is False
        assert agent.priority == 99
