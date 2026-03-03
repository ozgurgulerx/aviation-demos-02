"""Crew Recovery tools — availability, duty limits via SQL + AI Search."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import FAR_117_LIMITS, CREW_SCHEDULING_SOPS

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
    source_citations: List[Any] = []
    if _retriever:
        query = f"crew members at {base_airport} role {role} with remaining duty hours"
        rows, cits = await retriever_query(_retriever.query_sql(query))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"available_crew": rows[:15], "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide crew scheduling SOPs
    return attach_source_errors({
        "base": base_airport,
        "role": role,
        "available_crew": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No crew availability records found for {base_airport}. Use the scheduling SOPs "
            "and reserve crew procedures below to recommend crew sourcing strategies."
        ),
        "scheduling_sops": CREW_SCHEDULING_SOPS,
        "scenario_estimates": {
            "base_airport": base_airport,
            "role_queried": role,
            "reserve_response_time": CREW_SCHEDULING_SOPS["reserve_crew"]["airport_standby_response"],
            "sourcing_priority": CREW_SCHEDULING_SOPS["pairing_guidelines"]["priority_order"],
        },
    }, source_citations)


@ai_function(approval_mode="never_require")
async def check_duty_limits(
    crew_ids: Annotated[List[str], Field(description="Crew member IDs to check")],
) -> Dict[str, Any]:
    """Check FAR 117 duty and rest limits for specified crew members."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"duty hours and rest periods for crew {', '.join(crew_ids[:5])}"
        (sql_rows, sql_cits), (reg_rows, reg_cits) = await asyncio.gather(
            retriever_query(_retriever.query_sql(query)),
            retriever_query(_retriever.query_semantic("FAR 117 duty time limitations", source="VECTOR_REG")),
        )
        source_citations = sql_cits + reg_cits
        if sql_rows or reg_rows:
            return attach_source_errors({
                "crew_status": sql_rows[:10],
                "regulations": reg_rows[:3],
                "citations": [c.__dict__ for c in sql_cits + reg_cits],
            }, source_citations)
    # Fallback: provide FAR 117 duty limits
    return attach_source_errors({
        "crew_ids": crew_ids,
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No duty records found for these crew members. Use the FAR 117 limits below "
            "and the scenario context to assess duty limit compliance."
        ),
        "far_117_limits": FAR_117_LIMITS,
    }, source_citations)


@ai_function(approval_mode="never_require")
async def propose_crew_pairing(
    flight_id: Annotated[str, Field(description="Flight identifier needing crew")],
    required_roles: Annotated[List[str], Field(description="Roles needed")] = None,
) -> Dict[str, Any]:
    """Propose a crew pairing for a flight based on availability and qualifications."""
    source_citations: List[Any] = []
    if _retriever:
        query = f"crew pairing options for flight {flight_id}"
        rows, cits = await retriever_query(_retriever.query_sql(query))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"proposed_pairing": rows[:5], "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide pairing guidelines
    roles = required_roles or ["captain", "first_officer"]
    return attach_source_errors({
        "flight_id": flight_id,
        "roles": roles,
        "status": "no_data_fallback",
        "no_data_guidance": (
            f"No crew pairing data found for flight {flight_id}. Use the standard pairing "
            "guidelines and minimum complement requirements below to propose a crew solution."
        ),
        "pairing_guidelines": CREW_SCHEDULING_SOPS["pairing_guidelines"],
        "minimum_complement": CREW_SCHEDULING_SOPS["minimum_complement"],
    }, source_citations)
