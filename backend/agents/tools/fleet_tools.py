"""Fleet Recovery tools — aircraft availability, tail swaps via SQL + GRAPH."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import FLEET_RECOVERY_GUIDANCE

logger = structlog.get_logger()
_retriever = None

def set_retriever(r):
    global _retriever
    _retriever = r


@ai_function(approval_mode="never_require")
async def find_available_tails(
    aircraft_type: Annotated[str, Field(description="Aircraft type (e.g., B737, A320)")],
    base_airport: Annotated[str, Field(description="Airport IATA code where aircraft is needed")],
) -> Dict[str, Any]:
    """Find available aircraft tails of the specified type at or near the base airport."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"available {aircraft_type} aircraft at {base_airport} not assigned to active flights"
        rows, cits = await retriever_query(_retriever.query_sql(query))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"available_tails": rows[:10], "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide fleet availability estimation guidance
    is_wide_body = aircraft_type.upper().startswith(("B77", "B78", "A33", "A35", "A38"))
    spare_ratio = "3-5%" if is_wide_body else "5-8%"
    return attach_source_errors({
        "aircraft_type": aircraft_type,
        "base": base_airport,
        "available_tails": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No available {aircraft_type} tails found at {base_airport} in the database. "
            "Use the fleet availability estimates and ground time minimums below to reason "
            "about likely spare aircraft availability."
        ),
        "fleet_availability_estimation": FLEET_RECOVERY_GUIDANCE["fleet_availability_estimation"],
        "ground_time_minimums": FLEET_RECOVERY_GUIDANCE["ground_time_minimums"],
        "scenario_estimates": {
            "base_airport": base_airport,
            "aircraft_type": aircraft_type,
            "spare_ratio": spare_ratio,
            "typical_turnaround": FLEET_RECOVERY_GUIDANCE["ground_time_minimums"].get(
                "wide_body_domestic" if is_wide_body else "narrow_body_domestic",
                "45-60 minutes",
            ),
        },
    }, source_citations)


@ai_function(approval_mode="never_require")
async def check_range_compatibility(
    tailnum: Annotated[str, Field(description="Aircraft tail number")],
    route: Annotated[str, Field(description="Route pair (e.g., ORD-LAX)")],
) -> Dict[str, Any]:
    """Check if an aircraft has range/payload capability for a specific route."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"aircraft {tailnum} range capability for route {route} distance"
        rows, cits = await retriever_query(_retriever.query_sql(query))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"details": rows[:5], "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide evaluation criteria (keep compatible=unknown for safety)
    return attach_source_errors({
        "tailnum": tailnum,
        "route": route,
        "compatible": "unknown",
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No range/payload data found for {tailnum} on route {route}. "
            "Use the tail swap evaluation criteria and regulatory references below "
            "to assess compatibility based on known aircraft type characteristics."
        ),
        "swap_evaluation_criteria": FLEET_RECOVERY_GUIDANCE["tail_swap_evaluation_criteria"],
        "regulatory_refs": FLEET_RECOVERY_GUIDANCE["regulatory_refs"],
    }, source_citations)


@ai_function(approval_mode="never_require")
async def evaluate_tail_swap(
    original_tail: Annotated[str, Field(description="Original aircraft tail number")],
    swap_tail: Annotated[str, Field(description="Proposed swap aircraft tail number")],
    flight_id: Annotated[str, Field(description="Flight identifier")],
) -> Dict[str, Any]:
    """Evaluate a tail swap — MEL status, downstream impact, crew compatibility."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"MEL status and downstream flights for aircraft {swap_tail}"
        (sql_rows, sql_cits), (graph_rows, graph_cits) = await asyncio.gather(
            retriever_query(_retriever.query_sql(query)),
            retriever_query(_retriever.query_graph(f"downstream flights from {swap_tail}")),
        )
        source_citations = sql_cits + graph_cits
        mel_items = [r for r in sql_rows if "mel" in str(r).lower()][:5]
        if sql_rows or graph_rows:
            return attach_source_errors({
                "mel_items": mel_items,
                "downstream_impact": graph_rows[:10],
                "citations": [c.__dict__ for c in sql_cits + graph_cits],
            }, source_citations)
    # Fallback: provide MEL assessment guidance (keep feasible=unknown for safety)
    return attach_source_errors({
        "original": original_tail,
        "swap": swap_tail,
        "flight": flight_id,
        "feasible": "unknown",
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No MEL or schedule data found for swap aircraft {swap_tail}. "
            "Use the MEL category definitions and swap evaluation criteria below "
            "to assess feasibility based on scenario context."
        ),
        "mel_assessment_guidance": FLEET_RECOVERY_GUIDANCE["mel_categories"],
        "swap_evaluation_criteria": FLEET_RECOVERY_GUIDANCE["tail_swap_evaluation_criteria"],
    }, source_citations)
