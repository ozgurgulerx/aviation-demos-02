"""Tests for retriever wiring and safety-critical mock returns."""

from __future__ import annotations

import pytest

from agents.tools import RETRIEVER_MODULES
from agents.tools import (
    crew_tools,
    fatigue_tools,
    regulatory_tools,
    diversion_tools,
    fleet_tools,
    network_tools,
    weather_safety_tools,
    passenger_tools,
)

# ---------- Retriever wiring ----------


def test_all_modules_have_set_retriever():
    """Every RETRIEVER_MODULE must expose set_retriever()."""
    for mod in RETRIEVER_MODULES:
        assert hasattr(mod, "set_retriever"), f"{mod.__name__} missing set_retriever"
        assert callable(mod.set_retriever), f"{mod.__name__}.set_retriever not callable"


def test_all_modules_have_retriever_attr():
    """Every RETRIEVER_MODULE must have a _retriever attribute."""
    for mod in RETRIEVER_MODULES:
        assert hasattr(mod, "_retriever"), f"{mod.__name__} missing _retriever attribute"


# ---------- Safety-critical mock returns ----------

# Map of (module, function_name, kwargs) -> fields that must NOT be True in mock mode.
SAFETY_CRITICAL_MOCK_CASES = [
    (crew_tools, "check_duty_limits", {"crew_ids": ["C001"]}, ["all_within_limits"]),
    (fatigue_tools, "check_far117_compliance", {"crew_id": "C001", "proposed_duty_hours": 4.0}, ["compliant"]),
    (regulatory_tools, "check_compliance", {"action_description": "test action"}, ["compliant"]),
    (diversion_tools, "check_airport_capability", {"airport": "ORD", "aircraft_type": "B737"}, ["suitable"]),
    (fleet_tools, "check_range_compatibility", {"tailnum": "N12345", "route": "ORD-LAX"}, ["compatible"]),
    (fleet_tools, "evaluate_tail_swap", {"original_tail": "N111", "swap_tail": "N222", "flight_id": "AA100"}, ["feasible"]),
]


@pytest.fixture(autouse=True)
def _clear_retrievers():
    """Ensure all tool modules have _retriever=None for mock-path tests, then restore."""
    originals = {mod: getattr(mod, "_retriever", None) for mod in RETRIEVER_MODULES}
    for mod in RETRIEVER_MODULES:
        mod.set_retriever(None)
    yield
    for mod, orig in originals.items():
        mod.set_retriever(orig)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mod,func_name,kwargs,critical_fields",
    SAFETY_CRITICAL_MOCK_CASES,
    ids=[f"{m.__name__}.{f}" for m, f, _, _ in SAFETY_CRITICAL_MOCK_CASES],
)
async def test_mock_returns_not_optimistic(mod, func_name, kwargs, critical_fields):
    """Safety-critical mock returns must NOT be True — should be 'unknown' or similar."""
    func = getattr(mod, func_name)
    result = await func(**kwargs)
    for field in critical_fields:
        assert result.get(field) is not True, (
            f"{mod.__name__}.{func_name} mock returns {field}=True (optimistic). "
            f"Safety-critical mocks must return 'unknown' or equivalent."
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mod,func_name,kwargs,critical_fields",
    SAFETY_CRITICAL_MOCK_CASES,
    ids=[f"{m.__name__}.{f}" for m, f, _, _ in SAFETY_CRITICAL_MOCK_CASES],
)
async def test_mock_returns_include_status_mock(mod, func_name, kwargs, critical_fields):
    """All mock/fallback returns must include a non-empty status indicator."""
    func = getattr(mod, func_name)
    result = await func(**kwargs)
    assert result.get("status") in ("mock", "no_data_fallback"), (
        f"{mod.__name__}.{func_name} mock return missing status indicator, got: {result.get('status')!r}"
    )


# ---------- Fallback validation: no_data_fallback + non-empty guidance ----------

FALLBACK_CASES = [
    # fleet_tools
    (fleet_tools, "find_available_tails", {"aircraft_type": "B737", "base_airport": "ORD"}),
    (fleet_tools, "check_range_compatibility", {"tailnum": "N12345", "route": "ORD-LAX"}),
    (fleet_tools, "evaluate_tail_swap", {"original_tail": "N111", "swap_tail": "N222", "flight_id": "AA100"}),
    # network_tools
    (network_tools, "simulate_delay_propagation", {"origin_airport": "ORD", "delay_minutes": 60}),
    (network_tools, "query_historical_delays", {"airport": "ORD", "cause": "weather"}),
    # weather_safety_tools
    (weather_safety_tools, "check_sigmets_pireps", {"airports": ["ORD", "DFW"]}),
    (weather_safety_tools, "query_notams", {"airports": ["ORD"]}),
    (weather_safety_tools, "search_asrs_precedent", {"incident_description": "hub disruption due to weather"}),
    # passenger_tools
    (passenger_tools, "assess_connection_risks", {"flight_ids": ["AA100", "AA200"]}),
    (passenger_tools, "estimate_rebooking_load", {"airport": "ORD", "cancelled_flights": 5}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mod,func_name,kwargs",
    FALLBACK_CASES,
    ids=[f"{m.__name__}.{f}" for m, f, _ in FALLBACK_CASES],
)
async def test_fallback_returns_no_data_status(mod, func_name, kwargs):
    """Fallback returns must have status='no_data_fallback' and non-empty no_data_guidance."""
    func = getattr(mod, func_name)
    result = await func(**kwargs)
    assert result.get("status") == "no_data_fallback", (
        f"{mod.__name__}.{func_name} expected status='no_data_fallback', got: {result.get('status')!r}"
    )
    guidance = result.get("no_data_guidance", "")
    assert guidance and len(guidance) > 10, (
        f"{mod.__name__}.{func_name} no_data_guidance is missing or too short: {guidance!r}"
    )
