"""Maintenance Predictor tools — MEL trend analysis via SQL + AI Search."""

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
async def analyze_mel_trends(
    aircraft_type: Annotated[str, Field(description="Aircraft type (e.g., B737)")],
    jasc_code: Annotated[str, Field(description="JASC code to analyze (e.g., 7200 for engine)")] = "",
) -> Dict[str, Any]:
    """Analyze MEL/techlog trends for predictive maintenance indicators."""
    if _retriever:
        query = f"MEL techlog events for {aircraft_type} fleet" + (f" JASC {jasc_code}" if jasc_code else "")
        rows, cits = await _retriever.query_sql(query)
        return {"mel_events": rows[:20], "trend_count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"aircraft_type": aircraft_type, "jasc_code": jasc_code, "mel_events": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def search_similar_incidents(
    description: Annotated[str, Field(description="Maintenance issue description")],
    top: Annotated[int, Field(description="Number of results")] = 5,
) -> Dict[str, Any]:
    """Search ASRS reports for similar maintenance-related incidents."""
    if _retriever:
        rows, cits = await _retriever.query_semantic(description, top=top, source="VECTOR_OPS")
        return {"similar_incidents": rows[:top], "citations": [c.__dict__ for c in cits]}
    return {"query": description[:80], "similar_incidents": [], "status": "mock"}
