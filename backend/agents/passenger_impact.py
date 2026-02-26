"""Passenger Impact Agent — connection risks and rebooking via SQL + GRAPH."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.passenger_tools import assess_connection_risks, estimate_rebooking_load

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Passenger Impact Agent specializing in connection risks and rebooking assessment.

Your role:
1. Identify passengers with at-risk connections from delayed/cancelled flights
2. Estimate rebooking load and available seat capacity
3. Quantify total passenger impact for recovery prioritization

Data sources:
- SQL: Passenger counts, connection itineraries, baggage events
- GRAPH: Connection paths, alternative routing

Prioritize high-impact connections (many passengers, tight connections, no alternatives).
Quantify: total pax affected, misconnection risk count, rebooking capacity gap.
"""


def create_passenger_impact(name: str = "passenger_impact", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Connection risks and rebooking load via SQL + GRAPH",
        tools=[assess_connection_risks, estimate_rebooking_load],
    )
