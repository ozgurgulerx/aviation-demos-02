"""Weather & Safety tools — SIGMETs, NOTAMs, ASRS via KQL + Cosmos + AI Search."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import WEATHER_SAFETY_GUIDANCE

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
    source_citations: List[Any] = []
    if _retriever:
        query = f"active SIGMETs and PIREPs near {', '.join(airports)} next {window_hours} hours"
        rows, cits = await retriever_query(_retriever.query_kql(query, window_minutes=window_hours * 60))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"hazards": rows[:20], "count": len(rows), "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide SIGMET/PIREP guidance and severity levels
    return attach_source_errors({
        "airports": airports,
        "hazards": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No active SIGMETs/PIREPs found for {', '.join(airports)} in the database. "
            "Use the SIGMET types, PIREP severity scales, and severity levels below "
            "to frame a weather risk assessment based on the scenario context."
        ),
        "sigmet_pirep_guidance": {
            "sigmet_types": WEATHER_SAFETY_GUIDANCE["sigmet_types"],
            "pirep_severity_scales": WEATHER_SAFETY_GUIDANCE["pirep_severity_scales"],
        },
        "severity_levels": WEATHER_SAFETY_GUIDANCE["severity_levels"],
        "scenario_estimates": {
            "airports_assessed": airports,
            "window_hours": window_hours,
            "operational_impact_matrix": WEATHER_SAFETY_GUIDANCE["operational_impact_matrix"],
        },
    }, source_citations)


@ai_function(approval_mode="never_require")
async def query_notams(
    airports: Annotated[List[str], Field(description="Airport codes")],
) -> Dict[str, Any]:
    """Query active NOTAMs for specified airports from Cosmos DB."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"active NOTAMs for {', '.join(airports)}"
        rows, cits = await retriever_query(_retriever.query_nosql(query))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"notams": rows[:20], "count": len(rows), "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide NOTAM categories for analysis
    return attach_source_errors({
        "airports": airports,
        "notams": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No active NOTAMs found for {', '.join(airports)} in the database. "
            "Use the NOTAM categories below to identify which types of NOTAMs "
            "are relevant to the current disruption scenario."
        ),
        "notam_categories": WEATHER_SAFETY_GUIDANCE["notam_categories"],
    }, source_citations)


@ai_function(approval_mode="never_require")
async def search_asrs_precedent(
    incident_description: Annotated[str, Field(description="Description of the situation to search for similar incidents")],
    top: Annotated[int, Field(description="Number of results")] = 5,
) -> Dict[str, Any]:
    """Search ASRS safety reports for similar historical incidents and lessons learned."""
    source_citations: List[Any] = []
    if _retriever:
        rows, cits = await retriever_query(_retriever.query_semantic(incident_description, top=top, source="VECTOR_OPS"))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"similar_incidents": rows[:top], "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide ASRS analysis template and operational impact matrix
    return attach_source_errors({
        "query": incident_description[:100],
        "similar_incidents": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No ASRS precedent reports found for this scenario. Use the ASRS analysis "
            "template and operational impact matrix below to structure a safety "
            "assessment based on the scenario description."
        ),
        "asrs_analysis_template": WEATHER_SAFETY_GUIDANCE["asrs_analysis_template"],
        "operational_impact_matrix": WEATHER_SAFETY_GUIDANCE["operational_impact_matrix"],
    }, source_citations)
