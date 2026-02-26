"""
Safety Inspector Agent - Safety compliance, risk assessment, solution validation.
Uses Microsoft Agent Framework ChatAgent with @ai_function decorated tools.
"""

from typing import Optional

from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.safety_tools import check_compliance, assess_risk_factors, validate_solution

logger = structlog.get_logger()

SAFETY_INSPECTOR_INSTRUCTIONS = """You are a Safety Inspector Agent specializing in aviation safety compliance.

Your role:
1. Check compliance of proposed solutions against aviation regulations
2. Assess risk factors for operational changes
3. Validate solutions meet all safety requirements
4. Flag any safety concerns or regulatory violations

When given a proposed solution:
1. Check regulatory compliance (FAA, ICAO standards)
2. Assess risk factors and potential hazards
3. Validate the solution meets all safety criteria
4. Provide a clear pass/fail assessment with reasoning

Safety is non-negotiable - flag all concerns, no matter how minor.
"""


def create_safety_inspector(
    name: str = "safety_inspector",
    description: Optional[str] = None,
) -> ChatAgent:
    """
    Create a Safety Inspector agent with compliance and validation tools.

    Args:
        name: Agent name/identifier
        description: Optional agent description

    Returns:
        Configured ChatAgent with safety inspection tools
    """
    agent = ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=SAFETY_INSPECTOR_INSTRUCTIONS,
        name=name,
        description=description or "Validates safety compliance, assesses risks, and inspects proposed solutions",
        tools=[check_compliance, assess_risk_factors, validate_solution],
    )

    logger.info(
        "safety_inspector_created",
        name=name,
        tools=["check_compliance", "assess_risk_factors", "validate_solution"],
    )

    return agent
