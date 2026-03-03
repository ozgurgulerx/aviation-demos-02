"""
Aviation agent tools — module exports for retriever wiring.
"""

from agents.tools import (
    crew_tools,
    diversion_tools,
    fatigue_tools,
    fleet_tools,
    flight_tools,
    maintenance_tools,
    monitor_tools,
    network_tools,
    operations_tools,
    passenger_tools,
    regulatory_tools,
    route_tools,
    safety_tools,
    situation_tools,
    weather_safety_tools,
)

# All modules that support set_retriever()
RETRIEVER_MODULES = [
    crew_tools,
    diversion_tools,
    fatigue_tools,
    fleet_tools,
    flight_tools,
    maintenance_tools,
    monitor_tools,
    network_tools,
    operations_tools,
    passenger_tools,
    regulatory_tools,
    route_tools,
    safety_tools,
    situation_tools,
    weather_safety_tools,
]
