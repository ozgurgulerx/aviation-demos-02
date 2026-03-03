"""Crew Fatigue tools — FAR 117 compliance via SQL + AI Search."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import retriever_query
from agents.tools.domain_knowledge import FAR_117_LIMITS, FATIGUE_RISK_FACTORS

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
        rows, cits = await retriever_query(_retriever.query_sql(query))
        if rows:
            return {"fatigue_assessments": rows[:10], "citations": [c.__dict__ for c in cits]}
    # Fallback: provide domain knowledge so the agent can still analyze
    return {
        "crew_ids": crew_ids,
        "fatigue_assessments": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No crew fatigue records found in the database. Use the following FAR 117 "
            "limits and SAFTE/FAST risk factors to assess fatigue based on the scenario context."
        ),
        "far_117_limits": FAR_117_LIMITS,
        "risk_factors": FATIGUE_RISK_FACTORS,
    }


@ai_function(approval_mode="never_require")
async def check_far117_compliance(
    crew_id: Annotated[str, Field(description="Crew member ID")],
    proposed_duty_hours: Annotated[float, Field(description="Proposed additional duty hours")],
) -> Dict[str, Any]:
    """Check if proposed duty extension complies with FAR 117 rest requirements."""
    if _retriever:
        query = f"current duty status for crew {crew_id}"
        (sql_rows, sql_cits), (reg_rows, reg_cits) = await asyncio.gather(
            retriever_query(_retriever.query_sql(query)),
            retriever_query(_retriever.query_semantic(
                "FAR 117 flight duty period limits rest requirements", source="VECTOR_REG"
            )),
        )
        if sql_rows or reg_rows:
            return {
                "crew_status": sql_rows[:3],
                "applicable_regulations": reg_rows[:3],
                "citations": [c.__dict__ for c in sql_cits + reg_cits],
            }
    # Fallback: provide compliance check template
    return {
        "crew_id": crew_id,
        "proposed_hours": proposed_duty_hours,
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No crew duty records or regulation documents retrieved. Use the FAR 117 FDP "
            "limits below to evaluate whether the proposed duty extension is compliant."
        ),
        "far_117_limits": FAR_117_LIMITS,
        "compliance_check_template": {
            "steps": [
                "1. Determine number of flight segments and report time to find applicable FDP limit",
                "2. Compare proposed_duty_hours against FDP table value",
                "3. Check if 10-hour minimum rest was provided before this duty period",
                "4. Verify cumulative limits: 60h/168h and 190h/672h",
                "5. Assess if unforeseen operational extension (max +2h) applies",
            ],
        },
    }
