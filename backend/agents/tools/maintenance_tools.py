"""Maintenance Predictor tools — MEL trend analysis via SQL + AI Search."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import retriever_query
from agents.tools.domain_knowledge import MAINTENANCE_PREDICTION_GUIDANCE

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
        rows, cits = await retriever_query(_retriever.query_sql(query))
        if rows:
            return {"mel_events": rows[:20], "trend_count": len(rows), "citations": [c.__dict__ for c in cits]}
    # Fallback: provide JASC code families and trend analysis guidance
    return {
        "aircraft_type": aircraft_type,
        "jasc_code": jasc_code,
        "mel_events": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No MEL/techlog data found for {aircraft_type} fleet in the database. "
            "Use the JASC code families, deferral escalation thresholds, and trend analysis "
            "framework below to produce a predictive maintenance assessment from scenario context."
        ),
        "jasc_code_families": MAINTENANCE_PREDICTION_GUIDANCE["jasc_code_families"],
        "deferral_escalation_thresholds": MAINTENANCE_PREDICTION_GUIDANCE["deferral_escalation_thresholds"],
        "trend_analysis_framework": MAINTENANCE_PREDICTION_GUIDANCE["trend_analysis_framework"],
    }


@ai_function(approval_mode="never_require")
async def search_similar_incidents(
    description: Annotated[str, Field(description="Maintenance issue description")],
    top: Annotated[int, Field(description="Number of results")] = 5,
) -> Dict[str, Any]:
    """Search ASRS reports for similar maintenance-related incidents."""
    if _retriever:
        rows, cits = await retriever_query(_retriever.query_semantic(description, top=top, source="VECTOR_OPS"))
        if rows:
            return {"similar_incidents": rows[:top], "citations": [c.__dict__ for c in cits]}
    # Fallback: provide inspection escalation criteria and regulatory refs
    return {
        "query": description[:80],
        "similar_incidents": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No similar ASRS incidents found. Use the inspection escalation criteria "
            "and regulatory references below to guide maintenance recommendations."
        ),
        "inspection_escalation_criteria": MAINTENANCE_PREDICTION_GUIDANCE["inspection_escalation_criteria"],
        "regulatory_refs": MAINTENANCE_PREDICTION_GUIDANCE["regulatory_refs"],
    }
