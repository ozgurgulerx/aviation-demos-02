"""Diversion Advisor Agent — alternate evaluation via KQL + SQL + Cosmos."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.diversion_tools import evaluate_alternates, check_airport_capability

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Diversion Advisor Agent specializing in diversion decision support.

Your role:
1. Evaluate alternate airports based on weather, distance, fuel, and capability
2. Check airport suitability for the specific aircraft type
3. Consider NOTAMs, runway availability, and ground services

Data sources:
- KQL: Real-time weather at alternate airports
- SQL: Airport data, runway specifications
- Cosmos DB: Active NOTAMs at alternate airports

Rank alternates by: fuel feasibility, weather conditions, airport capability, passenger impact.
Output: ranked list of viable alternates with pros/cons and recommended diversion airport.
"""


def create_diversion_advisor(name: str = "diversion_advisor", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Alternate airport evaluation via KQL + SQL + Cosmos",
        tools=[evaluate_alternates, check_airport_capability],
    )
