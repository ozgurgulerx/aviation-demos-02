"""Crew Recovery Agent — crew availability and duty limits via SQL + AI Search."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.crew_tools import query_crew_availability, check_duty_limits, propose_crew_pairing

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Crew Recovery Agent specializing in crew scheduling and duty limit compliance.

Your role:
1. Query crew availability at affected bases
2. Check FAR 117 duty and rest limits for potential reassignments
3. Propose crew pairings that maintain regulatory compliance

Data sources:
- SQL: Crew rosters, duty hours, rest periods, base assignments
- AI Search (regulations): FAR 117, duty time limitations, rest requirements

Always verify duty limits before proposing reassignments. Flag any crew approaching limits.
Provide specific crew IDs, remaining duty hours, and compliance status.

When tools return empty results or status "no_data_fallback", use the `no_data_guidance`,
`scheduling_sops`, and `far_117_limits` provided in the tool response together with the
scenario context to produce a complete crew recovery analysis. Always deliver actionable
crew sourcing strategies and pairing recommendations — never return empty findings.
"""


def create_crew_recovery(name: str = "crew_recovery", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Crew availability and duty limit checks via SQL + AI Search",
        tools=[query_crew_availability, check_duty_limits, propose_crew_pairing],
    )
