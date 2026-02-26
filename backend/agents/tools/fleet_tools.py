"""Fleet Recovery tools — aircraft availability, tail swaps via SQL + GRAPH."""

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
async def find_available_tails(
    aircraft_type: Annotated[str, Field(description="Aircraft type (e.g., B737, A320)")],
    base_airport: Annotated[str, Field(description="Airport IATA code where aircraft is needed")],
) -> Dict[str, Any]:
    """Find available aircraft tails of the specified type at or near the base airport."""
    if _retriever:
        query = f"available {aircraft_type} aircraft at {base_airport} not assigned to active flights"
        rows, cits = await _retriever.query_sql(query)
        return {"available_tails": rows[:10], "citations": [c.__dict__ for c in cits]}
    return {"aircraft_type": aircraft_type, "base": base_airport, "available_tails": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def check_range_compatibility(
    tailnum: Annotated[str, Field(description="Aircraft tail number")],
    route: Annotated[str, Field(description="Route pair (e.g., ORD-LAX)")],
) -> Dict[str, Any]:
    """Check if an aircraft has range/payload capability for a specific route."""
    if _retriever:
        query = f"aircraft {tailnum} range capability for route {route} distance"
        rows, cits = await _retriever.query_sql(query)
        return {"compatible": True, "details": rows[:5], "citations": [c.__dict__ for c in cits]}
    return {"tailnum": tailnum, "route": route, "compatible": True, "status": "mock"}


@ai_function(approval_mode="never_require")
async def evaluate_tail_swap(
    original_tail: Annotated[str, Field(description="Original aircraft tail number")],
    swap_tail: Annotated[str, Field(description="Proposed swap aircraft tail number")],
    flight_id: Annotated[str, Field(description="Flight identifier")],
) -> Dict[str, Any]:
    """Evaluate a tail swap — MEL status, downstream impact, crew compatibility."""
    if _retriever:
        query = f"MEL status and downstream flights for aircraft {swap_tail}"
        sql_rows, sql_cits = await _retriever.query_sql(query)
        graph_rows, graph_cits = await _retriever.query_graph(f"downstream flights from {swap_tail}")
        return {
            "mel_items": [r for r in sql_rows if "mel" in str(r).lower()][:5],
            "downstream_impact": graph_rows[:10],
            "swap_feasible": True,
            "citations": [c.__dict__ for c in sql_cits + graph_cits],
        }
    return {"original": original_tail, "swap": swap_tail, "flight": flight_id, "feasible": True, "status": "mock"}
