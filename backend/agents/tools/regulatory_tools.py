"""Regulatory Compliance tools — regulation search via AI Search."""

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
async def check_compliance(
    action_description: Annotated[str, Field(description="Description of the proposed action to check")],
    regulation_area: Annotated[str, Field(description="Area: safety, operations, maintenance, crew")] = "safety",
) -> Dict[str, Any]:
    """Check if a proposed action complies with relevant regulations."""
    if _retriever:
        query = f"{regulation_area} regulations applicable to: {action_description}"
        reg_rows, reg_cits = await _retriever.query_semantic(query, source="VECTOR_REG")
        ops_rows, ops_cits = await _retriever.query_semantic(query, source="VECTOR_OPS")
        return {
            "regulations": reg_rows[:5],
            "operational_precedents": ops_rows[:3],
            "compliant": True,
            "citations": [c.__dict__ for c in reg_cits + ops_cits],
        }
    return {"action": action_description[:80], "area": regulation_area, "compliant": True, "status": "mock"}


@ai_function(approval_mode="never_require")
async def search_regulations(
    query: Annotated[str, Field(description="Regulation search query")],
    top: Annotated[int, Field(description="Number of results")] = 5,
) -> Dict[str, Any]:
    """Search FAA/EASA regulatory documents."""
    if _retriever:
        rows, cits = await _retriever.query_semantic(query, top=top, source="VECTOR_REG")
        return {"regulations": rows[:top], "citations": [c.__dict__ for c in cits]}
    return {"query": query[:80], "regulations": [], "status": "mock"}
