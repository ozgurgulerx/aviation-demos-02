"""Crew Recovery tools — availability, duty limits via SQL + AI Search."""

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
async def query_crew_availability(
    base_airport: Annotated[str, Field(description="Crew base airport code")],
    role: Annotated[str, Field(description="Crew role: captain, first_officer, flight_attendant")] = "captain",
) -> Dict[str, Any]:
    """Query available crew members at a base airport who are within duty limits."""
    if _retriever:
        query = f"crew members at {base_airport} role {role} with remaining duty hours"
        rows, cits = await _retriever.query_sql(query)
        return {"available_crew": rows[:15], "citations": [c.__dict__ for c in cits]}
    return {"base": base_airport, "role": role, "available_crew": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def check_duty_limits(
    crew_ids: Annotated[List[str], Field(description="Crew member IDs to check")],
) -> Dict[str, Any]:
    """Check FAR 117 duty and rest limits for specified crew members."""
    if _retriever:
        query = f"duty hours and rest periods for crew {', '.join(crew_ids[:5])}"
        sql_rows, sql_cits = await _retriever.query_sql(query)
        reg_rows, reg_cits = await _retriever.query_semantic("FAR 117 duty time limitations", source="VECTOR_REG")
        return {
            "crew_status": sql_rows[:10],
            "regulations": reg_rows[:3],
            "citations": [c.__dict__ for c in sql_cits + reg_cits],
        }
    return {"crew_ids": crew_ids, "all_within_limits": True, "status": "mock"}


@ai_function(approval_mode="never_require")
async def propose_crew_pairing(
    flight_id: Annotated[str, Field(description="Flight identifier needing crew")],
    required_roles: Annotated[List[str], Field(description="Roles needed")] = None,
) -> Dict[str, Any]:
    """Propose a crew pairing for a flight based on availability and qualifications."""
    if _retriever:
        query = f"crew pairing options for flight {flight_id}"
        rows, cits = await _retriever.query_sql(query)
        return {"proposed_pairing": rows[:5], "citations": [c.__dict__ for c in cits]}
    return {"flight_id": flight_id, "roles": required_roles or ["captain", "first_officer"], "status": "mock"}
