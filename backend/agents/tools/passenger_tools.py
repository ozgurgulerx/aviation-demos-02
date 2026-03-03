"""Passenger Impact tools — connection risks, rebooking via SQL + GRAPH."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import PASSENGER_IMPACT_GUIDANCE, contextualize_passenger_fallback

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
    source_citations: List[Any] = []
    if _retriever:
        query = f"passengers with connections on flights {', '.join(flight_ids[:5])}"
        (sql_rows, sql_cits), (graph_rows, graph_cits) = await asyncio.gather(
            retriever_query(_retriever.query_sql(query)),
            retriever_query(_retriever.query_graph(
                f"connection paths from flights {', '.join(flight_ids[:3])}"
            )),
        )
        source_citations = sql_cits + graph_cits
        if sql_rows or graph_rows:
            return attach_source_errors({
                "at_risk_connections": sql_rows[:20],
                "connection_graph": graph_rows[:15],
                "total_pax_affected": sum(int(r.get("passengers", 0) or 0) for r in sql_rows[:20]),
                "citations": [c.__dict__ for c in sql_cits + graph_cits],
            }, source_citations)
    # Fallback: provide connection risk framework and rebooking estimates
    return attach_source_errors({
        "flight_ids": flight_ids,
        "at_risk": 0,
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No passenger connection data found for flights {', '.join(flight_ids[:5])}. "
            "Use the connection risk tiers, rebooking estimates, and prioritization tiers "
            "below to assess likely passenger impact based on the scenario context."
        ),
        "connection_risk_framework": {
            "risk_tiers": PASSENGER_IMPACT_GUIDANCE["connection_risk_tiers"],
            "minimum_connection_times": PASSENGER_IMPACT_GUIDANCE["minimum_connection_times"],
            "priority_factors": PASSENGER_IMPACT_GUIDANCE["priority_factors"],
        },
        "rebooking_estimates": {
            "capacity_benchmarks": PASSENGER_IMPACT_GUIDANCE["rebooking_capacity_benchmarks"],
            "avg_pax_per_flight": PASSENGER_IMPACT_GUIDANCE["average_pax_per_flight"],
            "time_estimates": PASSENGER_IMPACT_GUIDANCE["rebooking_time_estimates"],
        },
        "prioritization_tiers": PASSENGER_IMPACT_GUIDANCE["prioritization_tiers"],
    }, source_citations)


@ai_function(approval_mode="never_require")
async def estimate_rebooking_load(
    airport: Annotated[str, Field(description="Airport where rebooking is needed")],
    cancelled_flights: Annotated[int, Field(description="Number of cancelled flights")],
) -> Dict[str, Any]:
    """Estimate rebooking load and available seat capacity."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"available seats on upcoming flights from {airport}"
        rows, cits = await retriever_query(_retriever.query_sql(query))
        source_citations = cits
        if rows:
            return attach_source_errors({
                "available_capacity": rows[:15],
                "estimated_pax_needing_rebooking": cancelled_flights * 150,
                "citations": [c.__dict__ for c in cits],
            }, source_citations)
    # Fallback: provide rebooking benchmarks and passenger rights
    return attach_source_errors({
        "airport": airport,
        "cancelled": cancelled_flights,
        "rebooking_load": cancelled_flights * 150,
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No seat availability data found for {airport}. Use the rebooking capacity "
            f"benchmarks below to estimate capacity for {cancelled_flights} cancelled flights "
            f"(~{cancelled_flights * 150} displaced passengers)."
        ),
        "rebooking_benchmarks": PASSENGER_IMPACT_GUIDANCE["rebooking_capacity_benchmarks"],
        "passenger_rights": PASSENGER_IMPACT_GUIDANCE["passenger_rights"],
        "prioritization_tiers": PASSENGER_IMPACT_GUIDANCE["prioritization_tiers"],
        "scenario_estimates": contextualize_passenger_fallback(
            hub_airport=airport, cancelled_flights=cancelled_flights,
        ),
    }, source_citations)
