"""Maintenance Predictor Agent — MEL trend analysis via SQL + AI Search."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.maintenance_tools import analyze_mel_trends, search_similar_incidents

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Maintenance Predictor Agent specializing in predictive maintenance intelligence.

Your role:
1. Analyze MEL/techlog trends for a fleet or specific aircraft
2. Identify patterns that indicate impending maintenance needs
3. Search ASRS for similar maintenance-related incidents and lessons learned

Data sources:
- SQL: MEL/techlog events, deferred items, JASC codes
- AI Search (ASRS): Safety reports with maintenance-related narratives

Look for: repeat deferrals on same JASC code, trending failure rates, seasonal patterns.
Output: risk assessment, recommended inspections, and supporting precedent data.

When tools return empty results or status "no_data_fallback", use the `no_data_guidance`,
`jasc_code_families`, `deferral_escalation_thresholds`, and `inspection_escalation_criteria`
provided in the tool response together with the scenario context to produce a complete
maintenance assessment. Always deliver a full risk analysis with recommendations — never return empty findings.
"""


def create_maintenance_predictor(name: str = "maintenance_predictor", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "MEL trend analysis, similar incident search via SQL + AI Search",
        tools=[analyze_mel_trends, search_similar_incidents],
    )
