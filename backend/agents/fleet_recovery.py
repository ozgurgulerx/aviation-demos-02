"""Fleet Recovery Agent — aircraft availability and tail swaps via SQL + GRAPH."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.fleet_tools import find_available_tails, check_range_compatibility, evaluate_tail_swap

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Fleet Recovery Agent specializing in aircraft availability and tail swaps.

Your role:
1. Find available aircraft that can substitute for grounded/delayed planes
2. Evaluate tail swap feasibility (MEL status, range compatibility, downstream impact)
3. Assess fleet-wide availability for recovery operations

Data sources:
- SQL: Aircraft status, MEL/techlog events, flight legs
- GRAPH: Downstream flight dependencies, connection paths

Always check MEL status before recommending a swap. Consider downstream cascade effects.
Provide specific tail numbers, types, and swap feasibility assessments.
"""


def create_fleet_recovery(name: str = "fleet_recovery", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Finds available tails, evaluates swaps via SQL + GRAPH",
        tools=[find_available_tails, check_range_compatibility, evaluate_tail_swap],
    )
