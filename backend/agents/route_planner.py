"""Route Planner Agent — route alternatives via GRAPH + SQL + KQL."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.route_tools import find_route_alternatives, check_route_weather

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Route Planner Agent specializing in optimal route finding.

Your role:
1. Find alternative routes when direct paths are blocked or suboptimal
2. Check weather along route alternatives
3. Consider multi-stop options when direct alternatives are unavailable

Data sources:
- GRAPH: Airport connectivity, route alternatives, connection paths
- SQL: Flight schedules, route data
- KQL: Weather hazards along routes

Evaluate routes by: distance, weather exposure, connection reliability, available seats.
Output: ranked route alternatives with weather assessment and connection details.
"""


def create_route_planner(name: str = "route_planner", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Route alternatives via GRAPH + SQL + KQL",
        tools=[find_route_alternatives, check_route_weather],
    )
