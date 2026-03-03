"""Route Planner tools — route alternatives via GRAPH + SQL + KQL."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import ROUTE_PLANNING_GUIDANCE

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
    source_citations: List[Any] = []
    if _retriever:
        (graph_rows, graph_cits), (sql_rows, sql_cits) = await asyncio.gather(
            retriever_query(_retriever.query_graph(
                f"routes from {origin} to {destination}", hops=max_stops + 1
            )),
            retriever_query(_retriever.query_sql(
                f"flights from {origin} with connections to {destination}"
            )),
        )
        source_citations = graph_cits + sql_cits
        return attach_source_errors({
            "route_alternatives": graph_rows[:10],
            "available_flights": sql_rows[:15],
            "citations": [c.__dict__ for c in graph_cits + sql_cits],
        }, source_citations)
    return attach_source_errors({
        "origin": origin,
        "destination": destination,
        "alternatives": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No route alternative data retrieved for {origin}-{destination}. Use the route "
            "evaluation criteria and connection planning factors below together with the "
            "scenario context to recommend routing options."
        ),
        "route_evaluation_criteria": ROUTE_PLANNING_GUIDANCE["route_evaluation_criteria"],
        "connection_planning_factors": ROUTE_PLANNING_GUIDANCE["connection_planning_factors"],
    }, source_citations)


@ai_function(approval_mode="never_require")
async def check_route_weather(
    route: Annotated[str, Field(description="Route pair (e.g., ORD-LAX)")],
) -> Dict[str, Any]:
    """Check weather conditions along a route."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"weather hazards along route {route}"
        rows, cits = await retriever_query(_retriever.query_kql(query))
        source_citations = cits
        return attach_source_errors({"route_weather": rows[:15], "citations": [c.__dict__ for c in cits]}, source_citations)
    return attach_source_errors({
        "route": route,
        "route_weather": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No weather data retrieved for route {route}. Use the weather avoidance "
            "guidelines below to assess potential weather hazards along this route."
        ),
        "weather_avoidance_guidelines": ROUTE_PLANNING_GUIDANCE["weather_avoidance_guidelines"],
    }, source_citations)
