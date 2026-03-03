"""Situation Assessment tools — disruption scope mapping via GRAPH + SQL + KQL."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import retriever_query
from agents.tools.domain_knowledge import DISRUPTION_FRAMEWORK, contextualize_disruption_fallback

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
        (sql_rows, sql_cit), (graph_rows, graph_cit) = await asyncio.gather(
            retriever_query(_retriever.query_sql(query)),
            retriever_query(_retriever.query_graph(query, hops=2)),
        )
        if sql_rows or graph_rows:
            return {
                "affected_flights": sql_rows[:20],
                "network_connections": graph_rows[:15],
                "citations": [c.__dict__ for c in sql_cit + graph_cit],
                "scope": {"airports": airports, "window_hours": time_window_hours},
            }
    # Fallback: provide disruption assessment framework
    return {
        "airports": airports,
        "scope": {"airports": airports, "window_hours": time_window_hours},
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No flight disruption data retrieved for {', '.join(airports)}. Use the disruption "
            "assessment framework and typical hub metrics below along with the scenario context "
            "to estimate the scope of disruption."
        ),
        "disruption_framework": DISRUPTION_FRAMEWORK,
        "scenario_estimates": contextualize_disruption_fallback(
            airports=airports, time_window_hours=time_window_hours,
        ),
    }


@ai_function(approval_mode="never_require")
async def query_flight_schedule(
    airports: Annotated[List[str], Field(description="Airport codes")],
    status_filter: Annotated[str, Field(description="Filter: all, delayed, cancelled, diverted")] = "all",
) -> Dict[str, Any]:
    """Query flight schedule data for specified airports."""
    if _retriever:
        query = f"flight schedule at {', '.join(airports)} status {status_filter}"
        rows, cits = await retriever_query(_retriever.query_sql(query))
        if rows:
            return {"flights": rows[:30], "total": len(rows), "citations": [c.__dict__ for c in cits]}
    # Fallback: provide estimation heuristics
    return {
        "airports": airports,
        "filter": status_filter,
        "flights": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No flight schedule data retrieved. Use the estimation heuristics and typical "
            "hub metrics below to reason about the likely flight activity at these airports."
        ),
        "estimation_heuristics": DISRUPTION_FRAMEWORK["estimation_heuristics"],
        "typical_hub_metrics": DISRUPTION_FRAMEWORK["typical_hub_metrics"],
    }


@ai_function(approval_mode="never_require")
async def get_live_positions(
    airports: Annotated[List[str], Field(description="Airport codes to query positions near")],
) -> Dict[str, Any]:
    """Get real-time ADS-B flight positions near specified airports."""
    if _retriever:
        query = f"live aircraft positions near {', '.join(airports)}"
        rows, cits = await retriever_query(_retriever.query_kql(query, window_minutes=30))
        if rows:
            return {"positions": rows[:50], "count": len(rows), "citations": [c.__dict__ for c in cits]}
    # Fallback: note to use scenario context
    return {
        "airports": airports,
        "positions": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No live ADS-B position data available. Base your situational awareness on the "
            "scenario description and any flight schedule information already obtained."
        ),
    }
