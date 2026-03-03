"""Network Impact tools — delay propagation via Fabric SQL + GRAPH."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import retriever_query
from agents.tools.domain_knowledge import NETWORK_IMPACT_GUIDANCE

logger = structlog.get_logger()
_retriever = None

def set_retriever(r):
    global _retriever
    _retriever = r


@ai_function(approval_mode="never_require")
async def simulate_delay_propagation(
    origin_airport: Annotated[str, Field(description="Airport where delay originated")],
    delay_minutes: Annotated[int, Field(description="Initial delay in minutes")],
    cascade_hops: Annotated[int, Field(description="Number of downstream hops to simulate")] = 3,
) -> Dict[str, Any]:
    """Simulate how a delay propagates through the network."""
    if _retriever:
        graph_rows, graph_cits = await retriever_query(_retriever.query_graph(
            f"downstream connections from {origin_airport}", hops=cascade_hops
        ))
        if graph_rows:
            return {
                "origin": origin_airport,
                "initial_delay": delay_minutes,
                "cascade_paths": graph_rows[:20],
                "estimated_affected_flights": len(graph_rows),
                "citations": [c.__dict__ for c in graph_cits],
            }
    # Fallback: provide propagation model and cascade rules
    return {
        "origin": origin_airport,
        "delay": delay_minutes,
        "affected_flights": 0,
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No network graph data found for {origin_airport}. Use the delay propagation "
            "model and cascade estimation rules below to estimate downstream impact "
            f"for a {delay_minutes}-minute delay across {cascade_hops} hops."
        ),
        "propagation_model": NETWORK_IMPACT_GUIDANCE["propagation_model"],
        "cascade_rules": NETWORK_IMPACT_GUIDANCE["cascade_estimation_rules"],
    }


@ai_function(approval_mode="never_require")
async def query_historical_delays(
    airport: Annotated[str, Field(description="Airport code")],
    cause: Annotated[str, Field(description="Delay cause: weather, carrier, nas, security")] = "weather",
) -> Dict[str, Any]:
    """Query BTS historical delay data for pattern analysis."""
    if _retriever:
        query = f"average {cause} delays at {airport} from BTS on-time performance data"
        rows, cits = await retriever_query(_retriever.query_fabric_sql(query))
        if rows:
            return {"historical_delays": rows[:20], "citations": [c.__dict__ for c in cits]}
    # Fallback: provide BTS benchmarks for the requested cause
    benchmarks = NETWORK_IMPACT_GUIDANCE["bts_benchmarks_by_cause"]
    requested_cause_benchmark = benchmarks.get(cause, benchmarks["carrier"])
    return {
        "airport": airport,
        "cause": cause,
        "historical_delays": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No BTS historical delay data found for {airport}/{cause}. Use the national "
            "BTS benchmarks below as a baseline for this delay cause category."
        ),
        "bts_benchmarks": benchmarks,
        "requested_cause_benchmark": requested_cause_benchmark,
    }
