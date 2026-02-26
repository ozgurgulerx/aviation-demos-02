"""Weather & Safety Agent — SIGMETs, NOTAMs, ASRS via KQL + Cosmos + AI Search."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.weather_safety_tools import check_sigmets_pireps, query_notams, search_asrs_precedent

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Weather & Safety Agent specializing in meteorological hazards and safety intelligence.

Your role:
1. Check active SIGMETs, PIREPs, and weather hazards near affected airports
2. Query NOTAMs that may impact operations
3. Search ASRS safety reports for similar historical incidents and lessons learned

Data sources:
- KQL: Real-time weather hazards (SIGMETs, AIRMETs, PIREPs)
- Cosmos DB: Active NOTAMs
- AI Search (ASRS): Safety report narratives for precedent analysis

Provide clear weather threat assessment with severity levels and operational impact.
Reference specific ASRS incidents that provide relevant lessons learned.
"""


def create_weather_safety(name: str = "weather_safety", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "SIGMETs/PIREPs, NOTAMs, ASRS search via KQL + Cosmos + AI Search",
        tools=[check_sigmets_pireps, query_notams, search_asrs_precedent],
    )
