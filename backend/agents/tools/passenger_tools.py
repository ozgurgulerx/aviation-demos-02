"""Passenger Impact tools — connection risks, rebooking via SQL + GRAPH."""

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
async def assess_connection_risks(
    flight_ids: Annotated[List[str], Field(description="Affected flight IDs to check connections")],
) -> Dict[str, Any]:
    """Assess passenger connection risks for delayed/cancelled flights."""
    if _retriever:
        query = f"passengers with connections on flights {', '.join(flight_ids[:5])}"
        sql_rows, sql_cits = await _retriever.query_sql(query)
        graph_rows, graph_cits = await _retriever.query_graph(
            f"connection paths from flights {', '.join(flight_ids[:3])}"
        )
        return {
            "at_risk_connections": sql_rows[:20],
            "connection_graph": graph_rows[:15],
            "total_pax_affected": sum(int(r.get("passengers", 0) or 0) for r in sql_rows[:20]),
            "citations": [c.__dict__ for c in sql_cits + graph_cits],
        }
    return {"flight_ids": flight_ids, "at_risk": 0, "status": "mock"}


@ai_function(approval_mode="never_require")
async def estimate_rebooking_load(
    airport: Annotated[str, Field(description="Airport where rebooking is needed")],
    cancelled_flights: Annotated[int, Field(description="Number of cancelled flights")],
) -> Dict[str, Any]:
    """Estimate rebooking load and available seat capacity."""
    if _retriever:
        query = f"available seats on upcoming flights from {airport}"
        rows, cits = await _retriever.query_sql(query)
        return {
            "available_capacity": rows[:15],
            "estimated_pax_needing_rebooking": cancelled_flights * 150,
            "citations": [c.__dict__ for c in cits],
        }
    return {"airport": airport, "cancelled": cancelled_flights, "rebooking_load": cancelled_flights * 150, "status": "mock"}
