"""Situation Assessment Agent — maps disruption scope via GRAPH + SQL + KQL."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.situation_tools import map_disruption_scope, query_flight_schedule, get_live_positions

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Situation Assessment Agent specializing in disruption scope mapping.

Your role:
1. Map the full scope of an operational disruption
2. Identify all affected flights, gates, and connections
3. Query real-time flight positions when relevant
4. Provide a clear picture of the current situation

Data sources available:
- GRAPH: Airport/flight connectivity for understanding cascade impacts
- SQL: Flight schedules, status, passenger data
- KQL: Real-time ADS-B positions, weather hazards

Be systematic: first scope the disruption, then identify affected resources, finally summarize the impact.
Output structured findings with specific flight IDs, airport codes, and quantified impacts.
"""


def create_situation_assessment(name: str = "situation_assessment", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Maps disruption scope via GRAPH + SQL + KQL",
        tools=[map_disruption_scope, query_flight_schedule, get_live_positions],
    )
