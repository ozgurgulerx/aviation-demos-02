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
    def test_registry_has_twenty_agents(self):
        assert len(AGENT_REGISTRY) == 20

    def test_get_agent_registry_returns_copy(self):
        registry = get_agent_registry()
        assert len(registry) == 20

    def test_agent_ids_include_key_agents(self):
        ids = [a.id for a in AGENT_REGISTRY]
        assert "situation_assessment" in ids
        assert "fleet_recovery" in ids
        assert "recovery_coordinator" in ids
        assert "decision_coordinator" in ids

    def test_agent_categories(self):
        categories = {a.category for a in AGENT_REGISTRY}
        assert "specialist" in categories
        assert "coordinator" in categories

    def test_agent_priorities_ordered(self):
        priorities = [a.priority for a in AGENT_REGISTRY]
        assert priorities == sorted(priorities)

    def test_get_agent_by_id_found(self):
        agent = get_agent_by_id("situation_assessment")
        assert agent is not None
        assert agent.name == "Situation Assessment"
        assert agent.short_name == "Situation"

    def test_get_agent_by_id_not_found(self):
        agent = get_agent_by_id("nonexistent")
        assert agent is None


class TestAgentSelection:
    def test_select_agents_for_generic_problem(self):
        included, excluded = select_agents_for_problem("Flight delayed due to weather")
        assert len(included) >= 3
        assert len(included) + len(excluded) == 20

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
            assert result.category in {"specialist", "coordinator"}
            assert result.included is True
            assert result.reason
            assert len(result.conditions_evaluated) > 0

    def test_empty_problem_still_selects(self):
        included, excluded = select_agents_for_problem("")
        assert len(included) >= 3


class TestAgentDefinition:
    def test_agent_definition_model(self):
        agent = AgentDefinition(
            id="test_agent",
            name="Test Agent",
            short_name="Test",
            category="specialist",
            description="A test agent",
            default_include=False,
            priority=99,
        )
        assert agent.id == "test_agent"
        assert agent.default_include is False
        assert agent.priority == 99
