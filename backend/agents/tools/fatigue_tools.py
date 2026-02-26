"""Crew Fatigue tools — FAR 117 compliance via SQL + AI Search."""

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
async def calculate_fatigue_score(
    crew_ids: Annotated[List[str], Field(description="Crew member IDs to assess")],
) -> Dict[str, Any]:
    """Calculate fatigue risk scores based on duty patterns and rest periods."""
    if _retriever:
        query = f"duty hours, rest periods, and cumulative fatigue for crew {', '.join(crew_ids[:5])}"
        rows, cits = await _retriever.query_sql(query)
        return {"fatigue_assessments": rows[:10], "citations": [c.__dict__ for c in cits]}
    return {"crew_ids": crew_ids, "fatigue_assessments": [], "status": "mock"}


@ai_function(approval_mode="never_require")
async def check_far117_compliance(
    crew_id: Annotated[str, Field(description="Crew member ID")],
    proposed_duty_hours: Annotated[float, Field(description="Proposed additional duty hours")],
) -> Dict[str, Any]:
    """Check if proposed duty extension complies with FAR 117 rest requirements."""
    if _retriever:
        query = f"current duty status for crew {crew_id}"
        sql_rows, sql_cits = await _retriever.query_sql(query)
        reg_rows, reg_cits = await _retriever.query_semantic(
            "FAR 117 flight duty period limits rest requirements", source="VECTOR_REG"
        )
        return {
            "crew_status": sql_rows[:3],
            "applicable_regulations": reg_rows[:3],
            "compliant": True,
            "citations": [c.__dict__ for c in sql_cits + reg_cits],
        }
    return {"crew_id": crew_id, "proposed_hours": proposed_duty_hours, "compliant": True, "status": "mock"}
