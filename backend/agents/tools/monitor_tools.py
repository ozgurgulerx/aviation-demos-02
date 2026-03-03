"""Real-Time Monitor tools — live positions + NOTAMs via KQL + Cosmos."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import retriever_query
from agents.tools.domain_knowledge import REAL_TIME_MONITORING_GUIDANCE

logger = structlog.get_logger()
_retriever = None

def set_retriever(r):
    global _retriever
    _retriever = r


@ai_function(approval_mode="never_require")
async def get_live_positions(
    callsigns: Annotated[List[str], Field(description="Flight callsigns to track")] = None,
    airports: Annotated[List[str], Field(description="Airports to monitor")] = None,
) -> Dict[str, Any]:
    """Get real-time ADS-B positions for specified flights or near airports."""
    if _retriever:
        targets = callsigns or airports or ["ORD"]
        query = f"live ADS-B positions for {', '.join(targets[:5])}"
        rows, cits = await retriever_query(_retriever.query_kql(query, window_minutes=15))
        return {"positions": rows[:50], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {
        "callsigns": callsigns,
        "airports": airports,
        "positions": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No live ADS-B position data available. Use the ADS-B interpretation guide "
            "and typical flight parameters below to reason about expected aircraft positions "
            "based on the scenario context."
        ),
        "adsb_interpretation": REAL_TIME_MONITORING_GUIDANCE["adsb_interpretation"],
        "typical_flight_parameters": REAL_TIME_MONITORING_GUIDANCE["typical_flight_parameters"],
    }


@ai_function(approval_mode="never_require")
async def check_active_notams(
    airports: Annotated[List[str], Field(description="Airport codes to check NOTAMs")],
) -> Dict[str, Any]:
    """Check currently active NOTAMs for specified airports."""
    if _retriever:
        query = f"active NOTAMs at {', '.join(airports)}"
        rows, cits = await retriever_query(_retriever.query_nosql(query))
        return {"notams": rows[:20], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {
        "airports": airports,
        "notams": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No active NOTAM data retrieved for {', '.join(airports)}. Use the NOTAM "
            "priority framework and situational awareness template below to assess "
            "potential operational restrictions."
        ),
        "notam_priority_framework": REAL_TIME_MONITORING_GUIDANCE["notam_priority_framework"],
        "situational_awareness_template": REAL_TIME_MONITORING_GUIDANCE["situational_awareness_template"],
    }
