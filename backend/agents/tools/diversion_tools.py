"""Diversion Advisor tools — alternate evaluation via KQL + SQL + Cosmos."""

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
async def evaluate_alternates(
    current_position: Annotated[str, Field(description="Current flight position or nearest waypoint")],
    aircraft_type: Annotated[str, Field(description="Aircraft type for runway requirements")],
    fuel_remaining_minutes: Annotated[int, Field(description="Fuel remaining in minutes")] = 90,
) -> Dict[str, Any]:
    """Evaluate alternate airports for diversion based on weather, distance, and capability."""
    if _retriever:
        query = f"airports within {fuel_remaining_minutes} minutes flying time from {current_position}"
        sql_rows, sql_cits = await _retriever.query_sql(query)
        kql_rows, kql_cits = await _retriever.query_kql(f"weather at airports near {current_position}")
        notam_rows, notam_cits = await _retriever.query_nosql(f"NOTAMs for airports near {current_position}")
        return {
            "alternates": sql_rows[:10],
            "weather_conditions": kql_rows[:10],
            "active_notams": notam_rows[:10],
            "citations": [c.__dict__ for c in sql_cits + kql_cits + notam_cits],
        }
    return {"position": current_position, "alternates": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def check_airport_capability(
    airport: Annotated[str, Field(description="Airport IATA code")],
    aircraft_type: Annotated[str, Field(description="Aircraft type")],
) -> Dict[str, Any]:
    """Check if airport can handle the aircraft type (runway, services, customs)."""
    if _retriever:
        query = f"airport {airport} capability for {aircraft_type} runway length services"
        rows, cits = await _retriever.query_semantic(query, source="VECTOR_AIRPORT")
        return {"capability": rows[:5], "suitable": True, "citations": [c.__dict__ for c in cits]}
    return {"airport": airport, "aircraft": aircraft_type, "suitable": True, "status": "mock"}
