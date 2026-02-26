"""Weather & Safety tools — SIGMETs, NOTAMs, ASRS via KQL + Cosmos + AI Search."""

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
async def check_sigmets_pireps(
    airports: Annotated[List[str], Field(description="Airport codes to check weather for")],
    window_hours: Annotated[int, Field(description="Hours to look ahead")] = 12,
) -> Dict[str, Any]:
    """Check active SIGMETs and PIREPs near specified airports."""
    if _retriever:
        query = f"active SIGMETs and PIREPs near {', '.join(airports)} next {window_hours} hours"
        rows, cits = await _retriever.query_kql(query, window_minutes=window_hours * 60)
        return {"hazards": rows[:20], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"airports": airports, "hazards": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def query_notams(
    airports: Annotated[List[str], Field(description="Airport codes")],
) -> Dict[str, Any]:
    """Query active NOTAMs for specified airports from Cosmos DB."""
    if _retriever:
        query = f"active NOTAMs for {', '.join(airports)}"
        rows, cits = await _retriever.query_nosql(query)
        return {"notams": rows[:20], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"airports": airports, "notams": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def search_asrs_precedent(
    incident_description: Annotated[str, Field(description="Description of the situation to search for similar incidents")],
    top: Annotated[int, Field(description="Number of results")] = 5,
) -> Dict[str, Any]:
    """Search ASRS safety reports for similar historical incidents and lessons learned."""
    if _retriever:
        rows, cits = await _retriever.query_semantic(incident_description, top=top, source="VECTOR_OPS")
        return {"similar_incidents": rows[:top], "citations": [c.__dict__ for c in cits]}
    return {"query": incident_description[:100], "similar_incidents": [], "status": "mock"}
