"""
Aviation Multi-Agent System — 20-agent pool using Microsoft Agent Framework.
Each agent is a ChatAgent with specialized tools decorated with @ai_function.
"""

from agents.flight_analyst import create_flight_analyst
from agents.operations_advisor import create_operations_advisor
from agents.safety_inspector import create_safety_inspector
from agents.situation_assessment import create_situation_assessment
from agents.fleet_recovery import create_fleet_recovery
from agents.crew_recovery import create_crew_recovery
from agents.network_impact import create_network_impact
from agents.weather_safety import create_weather_safety
from agents.passenger_impact import create_passenger_impact
from agents.recovery_coordinator import create_recovery_coordinator
from agents.maintenance_predictor import create_maintenance_predictor
from agents.crew_fatigue_assessor import create_crew_fatigue_assessor
from agents.diversion_advisor import create_diversion_advisor
from agents.regulatory_compliance import create_regulatory_compliance
from agents.route_planner import create_route_planner
from agents.real_time_monitor import create_real_time_monitor
from agents.decision_coordinator import create_decision_coordinator
from agents.client import get_chat_client, get_shared_chat_client, get_orchestrator_chat_client


# Factory map: agent_id -> create function
# Used by workflows.py to dynamically instantiate agents
agent_factories = {
    # Legacy 3 agents
    "flight_analyst": create_flight_analyst,
    "operations_advisor": create_operations_advisor,
    "safety_inspector": create_safety_inspector,

    # Hub Disruption Recovery (7 agents)
    "situation_assessment": create_situation_assessment,
    "fleet_recovery": create_fleet_recovery,
    "crew_recovery": create_crew_recovery,
    "network_impact": create_network_impact,
    "weather_safety": create_weather_safety,
    "passenger_impact": create_passenger_impact,
    "recovery_coordinator": create_recovery_coordinator,

    # Cross-scenario specialists
    "maintenance_predictor": create_maintenance_predictor,
    "crew_fatigue_assessor": create_crew_fatigue_assessor,
    "diversion_advisor": create_diversion_advisor,
    "regulatory_compliance": create_regulatory_compliance,
    "route_planner": create_route_planner,
    "real_time_monitor": create_real_time_monitor,
    "decision_coordinator": create_decision_coordinator,

    # Placeholder agents (stub — return generic ChatAgent)
    "fuel_optimizer": lambda **kw: create_flight_analyst(name=kw.get("name", "fuel_optimizer")),
    "gate_optimizer": lambda **kw: create_flight_analyst(name=kw.get("name", "gate_optimizer")),
    "atc_flow_advisor": lambda **kw: create_flight_analyst(name=kw.get("name", "atc_flow_advisor")),
    "historical_analyst": lambda **kw: create_flight_analyst(name=kw.get("name", "historical_analyst")),
    "airport_ops_advisor": lambda **kw: create_flight_analyst(name=kw.get("name", "airport_ops_advisor")),
    "cost_analyst": lambda **kw: create_flight_analyst(name=kw.get("name", "cost_analyst")),
}


__all__ = [
    "create_flight_analyst",
    "create_operations_advisor",
    "create_safety_inspector",
    "create_situation_assessment",
    "create_fleet_recovery",
    "create_crew_recovery",
    "create_network_impact",
    "create_weather_safety",
    "create_passenger_impact",
    "create_recovery_coordinator",
    "create_maintenance_predictor",
    "create_crew_fatigue_assessor",
    "create_diversion_advisor",
    "create_regulatory_compliance",
    "create_route_planner",
    "create_real_time_monitor",
    "create_decision_coordinator",
    "get_chat_client",
    "get_shared_chat_client",
    "get_orchestrator_chat_client",
    "agent_factories",
]
