"""Route Planner tools — route alternatives via GRAPH + SQL + KQL."""

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
async def find_route_alternatives(
    origin: Annotated[str, Field(description="Origin airport IATA code")],
    destination: Annotated[str, Field(description="Destination airport IATA code")],
    max_stops: Annotated[int, Field(description="Maximum number of stops")] = 1,
) -> Dict[str, Any]:
    """Find alternative routes between two airports."""
    if _retriever:
        graph_rows, graph_cits = await _retriever.query_graph(
            f"routes from {origin} to {destination}", hops=max_stops + 1
        )
        sql_rows, sql_cits = await _retriever.query_sql(
            f"flights from {origin} with connections to {destination}"
        )
        return {
            "route_alternatives": graph_rows[:10],
            "available_flights": sql_rows[:15],
            "citations": [c.__dict__ for c in graph_cits + sql_cits],
        }
    return {"origin": origin, "destination": destination, "alternatives": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def check_route_weather(
    route: Annotated[str, Field(description="Route pair (e.g., ORD-LAX)")],
) -> Dict[str, Any]:
    """Check weather conditions along a route."""
    if _retriever:
        query = f"weather hazards along route {route}"
        rows, cits = await _retriever.query_kql(query)
        return {"route_weather": rows[:15], "citations": [c.__dict__ for c in cits]}
    return {"route": route, "route_weather": [], "status": "mock"}
