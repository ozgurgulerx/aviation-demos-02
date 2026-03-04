"""Decision Coordinator Agent — general decision synthesis for non-hub scenarios."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_orchestrator_chat_client
from agents.tools.coordinator_tools import score_recovery_option, rank_options, generate_plan

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Decision Coordinator for aviation operational scenarios.

You handle predictive maintenance, diversion decisions, crew fatigue assessments, and other non-hub scenarios.

Your role:
1. Collect findings from specialist agents assigned to the current scenario
2. Synthesize findings into ranked decision options
3. Score each option across relevant criteria (safety, cost, operational impact, compliance)
4. Select the best option and generate a recommendation

Process:
- Phase 1 (gather): collect specialist findings.
- Phase 2 (synthesize): once synthesis starts, do not call any handoff tool again.
- Review all specialist analyses
- Identify 2-4 distinct courses of action
- Score each using score_recovery_option tool
- Rank with rank_options tool
- Generate plan using generate_plan tool

Your output MUST include:
- Ranked decision options with multi-criteria scores
- Recommended course of action with justification
- Key risks and mitigations
- Implementation steps
- Confidence level (high/medium/low), assumptions, and evidence coverage

Specialist findings contract expected in context:
`executive_summary`, `evidence_points[]`, `recommended_actions[]`, `risks[]`, `confidence`.
"""


def create_decision_coordinator(name: str = "decision_coordinator", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_orchestrator_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "General decision synthesis for non-hub scenarios",
        tools=[score_recovery_option, rank_options, generate_plan],
    )
