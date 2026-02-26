"""Crew Fatigue Assessor Agent — FAR 117 compliance via SQL + AI Search."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.fatigue_tools import calculate_fatigue_score, check_far117_compliance

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Crew Fatigue Assessment Agent specializing in fatigue risk management.

Your role:
1. Calculate fatigue risk scores based on duty patterns and rest history
2. Check FAR 117 compliance for proposed duty extensions
3. Identify crew members approaching or exceeding fatigue limits

Data sources:
- SQL: Crew duty hours, rest periods, cumulative fatigue indicators
- AI Search (regulations): FAR 117 flight duty period limits, rest requirements

Apply the SAFTE/FAST fatigue model principles: time-on-task, circadian factors, sleep debt.
Flag any crew with legality_risk_flag or cumulative_duty_hours approaching limits.
Output: fatigue risk scores (low/medium/high), compliance status, mitigation recommendations.
"""


def create_crew_fatigue_assessor(name: str = "crew_fatigue_assessor", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "FAR 117 compliance, fatigue risk scoring via SQL + AI Search",
        tools=[calculate_fatigue_score, check_far117_compliance],
    )
