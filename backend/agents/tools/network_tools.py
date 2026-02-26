"""Network Impact tools — delay propagation via Fabric SQL + GRAPH."""

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
async def simulate_delay_propagation(
    origin_airport: Annotated[str, Field(description="Airport where delay originated")],
    delay_minutes: Annotated[int, Field(description="Initial delay in minutes")],
    cascade_hops: Annotated[int, Field(description="Number of downstream hops to simulate")] = 3,
) -> Dict[str, Any]:
    """Simulate how a delay propagates through the network."""
    if _retriever:
        graph_rows, graph_cits = await _retriever.query_graph(
            f"downstream connections from {origin_airport}", hops=cascade_hops
        )
        return {
            "origin": origin_airport,
            "initial_delay": delay_minutes,
            "cascade_paths": graph_rows[:20],
            "estimated_affected_flights": len(graph_rows),
            "citations": [c.__dict__ for c in graph_cits],
        }
    return {"origin": origin_airport, "delay": delay_minutes, "affected_flights": 0, "status": "mock"}


@ai_function(approval_mode="never_require")
async def query_historical_delays(
    airport: Annotated[str, Field(description="Airport code")],
    cause: Annotated[str, Field(description="Delay cause: weather, carrier, nas, security")] = "weather",
) -> Dict[str, Any]:
    """Query BTS historical delay data for pattern analysis."""
    if _retriever:
        query = f"average {cause} delays at {airport} from BTS on-time performance data"
        rows, cits = await _retriever.query_fabric_sql(query)
        return {"historical_delays": rows[:20], "citations": [c.__dict__ for c in cits]}
    return {"airport": airport, "cause": cause, "historical_delays": [], "status": "mock"}
