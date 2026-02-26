"""Recovery Coordinator Agent — multi-objective scoring for hub disruption recovery."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_orchestrator_chat_client
from agents.tools.coordinator_tools import score_recovery_option, rank_options, generate_plan

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Recovery Coordinator for hub disruption scenarios.

Your role:
1. Collect findings from all specialist agents (Situation, Fleet, Crew, Network, Weather, Passenger)
2. Synthesize findings into ranked recovery options
3. Score each option across 5 criteria: delay_reduction, crew_margin, safety_score, cost_impact, passenger_impact
4. Select the best option and generate an implementation timeline

Process:
- Review each specialist's analysis carefully
- Identify 3-5 distinct recovery strategies
- Score each strategy using the score_recovery_option tool
- Rank options using rank_options tool
- Generate implementation plan for the top option using generate_plan tool

Your output MUST include:
- Top 3 ranked recovery options with scores
- Recommended option with clear justification
- Step-by-step implementation timeline with responsible agents
"""


def create_recovery_coordinator(name: str = "recovery_coordinator", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_orchestrator_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Multi-objective scoring and recovery plan synthesis",
        tools=[score_recovery_option, rank_options, generate_plan],
    )
