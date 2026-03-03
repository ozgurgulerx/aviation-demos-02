"""Diversion Advisor tools — alternate evaluation via KQL + SQL + Cosmos."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import DIVERSION_GUIDANCE

logger = structlog.get_logger()
_retriever = None

def set_retriever(r):
    global _retriever
    _retriever = r


@ai_function(approval_mode="never_require")
async def evaluate_alternates(
    current_position: Annotated[str, Field(description="Current flight position or nearest waypoint")],
    aircraft_type: Annotated[str, Field(description="Aircraft type for runway requirements")],
    fuel_remaining_minutes: Annotated[int, Field(description="Fuel remaining in minutes")] = 90,
) -> Dict[str, Any]:
    """Evaluate alternate airports for diversion based on weather, distance, and capability."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"airports within {fuel_remaining_minutes} minutes flying time from {current_position}"
        (sql_rows, sql_cits), (kql_rows, kql_cits), (notam_rows, notam_cits) = await asyncio.gather(
            retriever_query(_retriever.query_sql(query)),
            retriever_query(_retriever.query_kql(f"weather at airports near {current_position}")),
            retriever_query(_retriever.query_nosql(f"NOTAMs for airports near {current_position}")),
        )
        source_citations = sql_cits + kql_cits + notam_cits
        return attach_source_errors({
            "alternates": sql_rows[:10],
            "weather_conditions": kql_rows[:10],
            "active_notams": notam_rows[:10],
            "citations": [c.__dict__ for c in sql_cits + kql_cits + notam_cits],
        }, source_citations)
    return attach_source_errors({
        "position": current_position,
        "alternates": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No alternate airport data retrieved for position {current_position}. Use the "
            "alternate selection criteria, fuel planning factors, and airport capability matrix "
            "below together with the scenario context to evaluate diversion options."
        ),
        "alternate_selection_criteria": DIVERSION_GUIDANCE["alternate_selection_criteria"],
        "fuel_planning_factors": DIVERSION_GUIDANCE["fuel_planning_factors"],
        "airport_capability_matrix": DIVERSION_GUIDANCE["airport_capability_matrix"],
    }, source_citations)


@ai_function(approval_mode="never_require")
async def check_airport_capability(
    airport: Annotated[str, Field(description="Airport IATA code")],
    aircraft_type: Annotated[str, Field(description="Aircraft type")],
) -> Dict[str, Any]:
    """Check if airport can handle the aircraft type (runway, services, customs)."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"airport {airport} capability for {aircraft_type} runway length services"
        rows, cits = await retriever_query(_retriever.query_semantic(query, source="VECTOR_AIRPORT"))
        source_citations = cits
        return attach_source_errors({"capability": rows[:5], "citations": [c.__dict__ for c in cits]}, source_citations)
    return attach_source_errors({
        "airport": airport,
        "aircraft": aircraft_type,
        "suitable": "unknown",
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No capability data retrieved for {airport}. Use the airport capability matrix "
            "and regulatory references below to assess suitability for the aircraft type."
        ),
        "airport_capability_matrix": DIVERSION_GUIDANCE["airport_capability_matrix"],
        "regulatory_refs": DIVERSION_GUIDANCE["regulatory_refs"],
    }, source_citations)
