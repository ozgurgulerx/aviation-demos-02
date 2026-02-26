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
        result = await analyze_flight_data(flight_ids=["AA1234"])
        assert isinstance(result, dict)
        assert "flights" in result
        assert "AA1234" in result["flights"]

    @pytest.mark.asyncio
    async def test_check_weather_impact_returns_dict(self):
        result = await check_weather_impact(airports=["DFW"])
        assert isinstance(result, dict)
        assert "weather" in result
        assert "DFW" in result["weather"]

    @pytest.mark.asyncio
    async def test_query_route_status_returns_dict(self):
        result = await query_route_status(routes=["DFW-ORD"])
        assert isinstance(result, dict)
        assert "routes" in result
        assert "DFW-ORD" in result["routes"]


class TestOperationsTools:
    @pytest.mark.asyncio
    async def test_evaluate_alternatives_returns_dict(self):
        result = await evaluate_alternatives(problem_description="rebooking needed")
        assert isinstance(result, dict)
        assert "alternatives" in result

    @pytest.mark.asyncio
    async def test_optimize_resources_returns_dict(self):
        result = await optimize_resources(resource_type="crew")
        assert isinstance(result, dict)
        assert "optimization" in result

    @pytest.mark.asyncio
    async def test_calculate_impact_returns_dict(self):
        result = await calculate_impact(change_description="cancel flight AA1234")
        assert isinstance(result, dict)
        assert "affected_flights" in result


class TestSafetyTools:
    @pytest.mark.asyncio
    async def test_check_compliance_returns_dict(self):
        result = await check_compliance(solution_description="Rebook passengers on next available flight")
        assert isinstance(result, dict)
        assert "overall_compliant" in result

    @pytest.mark.asyncio
    async def test_assess_risk_factors_returns_dict(self):
        result = await assess_risk_factors(scenario_description="weather diversion scenario")
        assert isinstance(result, dict)
        assert "risks" in result

    @pytest.mark.asyncio
    async def test_validate_solution_returns_dict(self):
        result = await validate_solution(solution_description="Rebook passengers on next available flight")
        assert isinstance(result, dict)
        assert "solution" in result
