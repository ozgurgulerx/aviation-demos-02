"""Situation Assessment tools — disruption scope mapping via GRAPH + SQL + KQL."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog

logger = structlog.get_logger()

# Retriever injected at runtime
_retriever = None

def set_retriever(r):
    global _retriever
    _retriever = r


@ai_function(approval_mode="never_require")
async def map_disruption_scope(
    airports: Annotated[List[str], Field(description="Affected airport IATA codes")],
    time_window_hours: Annotated[int, Field(description="Hours to look back/forward")] = 6,
) -> Dict[str, Any]:
    """Map the scope of an operational disruption — affected flights, gates, and connections."""
    if _retriever:
        query = f"flights affected at {', '.join(airports)} within {time_window_hours} hours"
        sql_rows, sql_cit = await _retriever.query_sql(query)
        graph_rows, graph_cit = await _retriever.query_graph(query, hops=2)
        return {
            "affected_flights": sql_rows[:20],
            "network_connections": graph_rows[:15],
            "citations": [c.__dict__ for c in sql_cit + graph_cit],
            "scope": {"airports": airports, "window_hours": time_window_hours},
        }
    return {"airports": airports, "estimated_affected_flights": len(airports) * 12, "status": "mock"}


@ai_function(approval_mode="never_require")
async def query_flight_schedule(
    airports: Annotated[List[str], Field(description="Airport codes")],
    status_filter: Annotated[str, Field(description="Filter: all, delayed, cancelled, diverted")] = "all",
) -> Dict[str, Any]:
    """Query flight schedule data for specified airports."""
    if _retriever:
        query = f"flight schedule at {', '.join(airports)} status {status_filter}"
        rows, cits = await _retriever.query_sql(query)
        return {"flights": rows[:30], "total": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"airports": airports, "filter": status_filter, "flights": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def get_live_positions(
    airports: Annotated[List[str], Field(description="Airport codes to query positions near")],
) -> Dict[str, Any]:
    """Get real-time ADS-B flight positions near specified airports."""
    if _retriever:
        query = f"live aircraft positions near {', '.join(airports)}"
        rows, cits = await _retriever.query_kql(query, window_minutes=30)
        return {"positions": rows[:50], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    return {"airports": airports, "positions": [], "status": "mock"}
