"""Tests verifying parallelized data access in multi-source tool functions."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from agents.tools import (
    situation_tools,
    fleet_tools,
    diversion_tools,
    crew_tools,
    passenger_tools,
    route_tools,
    fatigue_tools,
    regulatory_tools,
)

ALL_TOOL_MODULES = [
    situation_tools, fleet_tools, diversion_tools, crew_tools,
    passenger_tools, route_tools, fatigue_tools, regulatory_tools,
]


class _FakeCit:
    def __init__(self):
        self.source = "test"
        self.text = "test citation"


def _make_retriever():
    """Create a mock retriever where each query method returns distinct data."""
    r = AsyncMock()
    cit = _FakeCit()
    for method in [
        "query_sql", "query_graph", "query_kql",
        "query_nosql", "query_semantic", "query_fabric_sql",
    ]:
        getattr(r, method).return_value = ([{"source": method}], [cit])
    r.query_multiple.return_value = {}
    return r


@pytest.fixture(autouse=True)
def _wire_and_cleanup():
    """Wire a fresh mock retriever per test, clean up after."""
    retriever = _make_retriever()
    originals = {}
    for mod in ALL_TOOL_MODULES:
        originals[mod] = getattr(mod, "_retriever", None)
        mod.set_retriever(retriever)
    yield retriever
    for mod, orig in originals.items():
        mod.set_retriever(orig)


# ---------- situation_tools.map_disruption_scope ----------

@pytest.mark.asyncio
async def test_situation_map_disruption_scope_calls_sql_and_graph(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await situation_tools.map_disruption_scope(airports=["ORD"])
    r.query_sql.assert_called_once()
    r.query_graph.assert_called_once()
    assert "affected_flights" in result
    assert "network_connections" in result


# ---------- fleet_tools.evaluate_tail_swap ----------

@pytest.mark.asyncio
async def test_fleet_evaluate_tail_swap_calls_sql_and_graph(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await fleet_tools.evaluate_tail_swap(
        original_tail="N111", swap_tail="N222", flight_id="AA100"
    )
    r.query_sql.assert_called_once()
    r.query_graph.assert_called_once()
    assert "mel_items" in result
    assert "downstream_impact" in result


# ---------- diversion_tools.evaluate_alternates ----------

@pytest.mark.asyncio
async def test_diversion_evaluate_alternates_calls_three_sources(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await diversion_tools.evaluate_alternates(
        current_position="KORD", aircraft_type="B737"
    )
    r.query_sql.assert_called_once()
    r.query_kql.assert_called_once()
    r.query_nosql.assert_called_once()
    assert "alternates" in result
    assert "weather_conditions" in result
    assert "active_notams" in result


# ---------- crew_tools.check_duty_limits ----------

@pytest.mark.asyncio
async def test_crew_check_duty_limits_calls_sql_and_semantic(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await crew_tools.check_duty_limits(crew_ids=["C001"])
    r.query_sql.assert_called_once()
    r.query_semantic.assert_called_once()
    assert "crew_status" in result
    assert "regulations" in result


# ---------- passenger_tools.assess_connection_risks ----------

@pytest.mark.asyncio
async def test_passenger_assess_connection_risks_calls_sql_and_graph(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await passenger_tools.assess_connection_risks(flight_ids=["AA100"])
    r.query_sql.assert_called_once()
    r.query_graph.assert_called_once()
    assert "at_risk_connections" in result
    assert "connection_graph" in result


# ---------- route_tools.find_route_alternatives ----------

@pytest.mark.asyncio
async def test_route_find_route_alternatives_calls_graph_and_sql(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await route_tools.find_route_alternatives(origin="ORD", destination="LAX")
    r.query_graph.assert_called_once()
    r.query_sql.assert_called_once()
    assert "route_alternatives" in result
    assert "available_flights" in result


# ---------- fatigue_tools.check_far117_compliance ----------

@pytest.mark.asyncio
async def test_fatigue_check_far117_calls_sql_and_semantic(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await fatigue_tools.check_far117_compliance(
        crew_id="C001", proposed_duty_hours=4.0
    )
    r.query_sql.assert_called_once()
    r.query_semantic.assert_called_once()
    assert "crew_status" in result
    assert "applicable_regulations" in result


# ---------- regulatory_tools.check_compliance ----------

@pytest.mark.asyncio
async def test_regulatory_check_compliance_calls_two_semantic_sources(_wire_and_cleanup):
    r = _wire_and_cleanup
    result = await regulatory_tools.check_compliance(
        action_description="extend crew duty"
    )
    assert r.query_semantic.call_count == 2
    assert "regulations" in result
    assert "operational_precedents" in result
