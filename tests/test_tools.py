"""
Tests for agent stub tools - verify return shapes and types.
"""

import pytest
from agents.tools.flight_tools import analyze_flight_data, check_weather_impact, query_route_status
from agents.tools.operations_tools import evaluate_alternatives, optimize_resources, calculate_impact
from agents.tools.safety_tools import check_compliance, assess_risk_factors, validate_solution


class TestFlightTools:
    @pytest.mark.asyncio
    async def test_analyze_flight_data_returns_dict(self):
        result = await analyze_flight_data(flight_number="AA1234")
        assert isinstance(result, dict)
        assert "flight_number" in result
        assert result["flight_number"] == "AA1234"

    @pytest.mark.asyncio
    async def test_check_weather_impact_returns_dict(self):
        result = await check_weather_impact(airport_code="DFW")
        assert isinstance(result, dict)
        assert "airport" in result
        assert result["airport"] == "DFW"

    @pytest.mark.asyncio
    async def test_query_route_status_returns_dict(self):
        result = await query_route_status(origin="DFW", destination="ORD")
        assert isinstance(result, dict)
        assert "origin" in result
        assert "destination" in result


class TestOperationsTools:
    @pytest.mark.asyncio
    async def test_evaluate_alternatives_returns_dict(self):
        result = await evaluate_alternatives(scenario="rebooking")
        assert isinstance(result, dict)
        assert "scenario" in result

    @pytest.mark.asyncio
    async def test_optimize_resources_returns_dict(self):
        result = await optimize_resources(resource_type="crew")
        assert isinstance(result, dict)
        assert "resource_type" in result

    @pytest.mark.asyncio
    async def test_calculate_impact_returns_dict(self):
        result = await calculate_impact(action="cancel_flight")
        assert isinstance(result, dict)
        assert "action" in result


class TestSafetyTools:
    @pytest.mark.asyncio
    async def test_check_compliance_returns_dict(self):
        result = await check_compliance(regulation="FAR-121")
        assert isinstance(result, dict)
        assert "regulation" in result

    @pytest.mark.asyncio
    async def test_assess_risk_factors_returns_dict(self):
        result = await assess_risk_factors(scenario="weather_diversion")
        assert isinstance(result, dict)
        assert "scenario" in result

    @pytest.mark.asyncio
    async def test_validate_solution_returns_dict(self):
        result = await validate_solution(solution_description="Rebook passengers on next available flight")
        assert isinstance(result, dict)
        assert "solution" in result
