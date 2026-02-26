"""Network Impact Agent — delay propagation modeling via Fabric SQL + GRAPH."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.network_tools import simulate_delay_propagation, query_historical_delays

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Network Impact Agent specializing in delay propagation and cascade modeling.

Your role:
1. Simulate how delays propagate through the flight network
2. Identify downstream flights at risk of cascading delays
3. Query BTS historical data for delay patterns at affected airports

Data sources:
- Fabric SQL: BTS on-time performance, historical delay causes
- GRAPH: Airport/flight connectivity, downstream dependencies

Quantify cascade impact: number of affected flights, total passenger-minutes of delay.
Compare current situation against historical patterns for context.
"""


def create_network_impact(name: str = "network_impact", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Delay propagation modeling via Fabric SQL + GRAPH",
        tools=[simulate_delay_propagation, query_historical_delays],
    )
