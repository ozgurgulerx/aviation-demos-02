"""Regulatory Compliance Agent — safety gate via AI Search."""

from typing import Optional
from agent_framework import ChatAgent
import structlog

from agents.client import get_shared_chat_client
from agents.tools.regulatory_tools import check_compliance, search_regulations

logger = structlog.get_logger()

INSTRUCTIONS = """You are the Regulatory Compliance Agent — the safety gate for all recovery plans.

Your role:
1. Check proposed actions against FAA/EASA regulations
2. Search regulatory documents for applicable rules
3. Validate that recovery plans meet safety and compliance standards

Data sources:
- AI Search (regulations): FAA FARs, EASA regulations, advisory circulars
- AI Search (operations): Operational safety standards, airline procedures

You are a safety gate — flag any proposed action that may violate regulations.
Be specific: cite regulation numbers, section references, and compliance requirements.
Output: compliance status (PASS/CAUTION/FAIL), applicable regulations, and any required mitigations.
"""


def create_regulatory_compliance(name: str = "regulatory_compliance", description: Optional[str] = None) -> ChatAgent:
    return ChatAgent(
        chat_client=get_shared_chat_client(),
        instructions=INSTRUCTIONS,
        name=name,
        description=description or "Safety gate — regulation search via AI Search",
        tools=[check_compliance, search_regulations],
    )
