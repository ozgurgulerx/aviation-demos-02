"""
Operations Advisor Agent - Operations optimization, resource allocation.
Uses Microsoft Agent Framework ChatAgent with @ai_function decorated tools.
"""

from typing import Optional

from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.operations_tools import evaluate_alternatives, optimize_resources, calculate_impact

logger = structlog.get_logger()

OPERATIONS_ADVISOR_INSTRUCTIONS = """You are an Operations Advisor Agent specializing in aviation operations optimization.

Your role:
1. Evaluate operational alternatives for disruption recovery
2. Optimize resource allocation (crew, aircraft, gates)
3. Calculate impact of proposed changes on operations
4. Recommend the most efficient operational strategies

When given a problem:
1. Evaluate the available alternatives
2. Optimize resource allocation for the best outcome
3. Calculate the operational impact of each option
4. Provide a clear recommendation with supporting data

Focus on practical, implementable solutions.
"""


def create_operations_advisor(
    name: str = "operations_advisor",
    description: Optional[str] = None,
) -> ChatAgent:
    """
    Create an Operations Advisor agent with optimization tools.

    Args:
        name: Agent name/identifier
        description: Optional agent description

    Returns:
        Configured ChatAgent with operations optimization tools
    """
    agent = ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=OPERATIONS_ADVISOR_INSTRUCTIONS,
        name=name,
        description=description or "Optimizes operations, resource allocation, and evaluates alternatives",
        tools=[evaluate_alternatives, optimize_resources, calculate_impact],
    )

    logger.info(
        "operations_advisor_created",
        name=name,
        tools=["evaluate_alternatives", "optimize_resources", "calculate_impact"],
    )

    return agent
