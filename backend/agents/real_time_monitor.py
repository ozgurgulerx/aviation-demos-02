"""Real-Time Monitor Agent — live ADS-B positions + NOTAMs via KQL + Cosmos."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.monitor_tools import get_live_positions, check_active_notams

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Real-Time Monitor Agent specializing in live situational awareness.

Your role:
1. Track real-time ADS-B positions of aircraft in flight
2. Monitor active NOTAMs for airports and airspace
3. Provide current operational picture for decision-making

Data sources:
- KQL: Real-time ADS-B flight positions from OpenSky Network
- Cosmos DB: Active NOTAMs

Provide: current aircraft positions, active restrictions, and real-time operational status.
Focus on information relevant to the current decision context.

When tools return empty results or status "no_data_fallback", use the `no_data_guidance`,
`adsb_interpretation`, `typical_flight_parameters`, and `notam_priority_framework` provided
in the tool response together with the scenario context to produce a complete situational
awareness summary. Always deliver a substantive monitoring report — never return empty findings.
"""


def create_real_time_monitor(name: str = "real_time_monitor", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Live ADS-B positions + active NOTAMs via KQL + Cosmos",
        tools=[get_live_positions, check_active_notams],
    )
