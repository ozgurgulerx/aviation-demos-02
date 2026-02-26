"""
Flight Analyst Agent - Analyzes flight data, schedule disruption patterns.
Uses Microsoft Agent Framework ChatAgent with @ai_function decorated tools.
"""

from typing import Optional

from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.flight_tools import analyze_flight_data, check_weather_impact, query_route_status

logger = structlog.get_logger()

FLIGHT_ANALYST_INSTRUCTIONS = """You are a Flight Analyst Agent specializing in aviation data analysis.

Your role:
1. Analyze flight data for patterns and anomalies
2. Identify schedule disruption patterns
3. Assess weather impact on operations
4. Query route statuses for operational awareness

When given a problem:
1. First analyze the relevant flight data
2. Check weather impacts if applicable
3. Query route statuses for affected routes
4. Summarize your findings with actionable insights

Be concise and data-driven in your responses.
"""


def create_flight_analyst(
    name: str = "flight_analyst",
    description: Optional[str] = None,
) -> ChatAgent:
    """
    Create a Flight Analyst agent with aviation data tools.

    Args:
        name: Agent name/identifier
        description: Optional agent description

    Returns:
        Configured ChatAgent with flight analysis tools
    """
    agent = ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=FLIGHT_ANALYST_INSTRUCTIONS,
        name=name,
        description=description or "Analyzes flight data, schedule disruption patterns, and route statuses",
        tools=[analyze_flight_data, check_weather_impact, query_route_status],
    )

    logger.info(
        "flight_analyst_created",
        name=name,
        tools=["analyze_flight_data", "check_weather_impact", "query_route_status"],
    )

    return agent
