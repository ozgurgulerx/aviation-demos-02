"""Real-Time Monitor tools — live positions + NOTAMs via KQL + Cosmos."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog

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
        rows, cits = await _retriever.query_kql(query, window_minutes=15)
        return {"positions": rows[:50], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"callsigns": callsigns, "airports": airports, "positions": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def check_active_notams(
    airports: Annotated[List[str], Field(description="Airport codes to check NOTAMs")],
) -> Dict[str, Any]:
    """Check currently active NOTAMs for specified airports."""
    if _retriever:
        query = f"active NOTAMs at {', '.join(airports)}"
        rows, cits = await _retriever.query_nosql(query)
        return {"notams": rows[:20], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"airports": airports, "notams": [], "status": "mock"}
