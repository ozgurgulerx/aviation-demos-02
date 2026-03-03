"""Regulatory Compliance tools — regulation search via AI Search."""

import asyncio
from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog
from agents.tools import attach_source_errors, retriever_query
from agents.tools.domain_knowledge import REGULATORY_REFERENCES

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
    source_citations: List[Any] = []
    if _retriever:
        query = f"{regulation_area} regulations applicable to: {action_description}"
        (reg_rows, reg_cits), (ops_rows, ops_cits) = await asyncio.gather(
            retriever_query(_retriever.query_semantic(query, source="VECTOR_REG")),
            retriever_query(_retriever.query_semantic(query, source="VECTOR_OPS")),
        )
        source_citations = reg_cits + ops_cits
        if reg_rows or ops_rows:
            return attach_source_errors({
                "regulations": reg_rows[:5],
                "operational_precedents": ops_rows[:3],
                "citations": [c.__dict__ for c in reg_cits + ops_cits],
            }, source_citations)
    # Fallback: provide key regulation references
    area_refs = REGULATORY_REFERENCES.get(regulation_area) or REGULATORY_REFERENCES.get("safety", {})
    return attach_source_errors({
        "action": action_description[:80],
        "area": regulation_area,
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No regulation documents retrieved from search. Use the key regulatory references "
            "below and your aviation domain knowledge to evaluate compliance of the proposed action."
        ),
        "applicable_regulations": area_refs,
        "all_regulation_areas": REGULATORY_REFERENCES,
    }, source_citations)


@ai_function(approval_mode="never_require")
async def search_regulations(
    query: Annotated[str, Field(description="Regulation search query")],
    top: Annotated[int, Field(description="Number of results")] = 5,
) -> Dict[str, Any]:
    """Search FAA/EASA regulatory documents."""
    source_citations: List[Any] = []
    if _retriever:
        rows, cits = await retriever_query(_retriever.query_semantic(query, top=top, source="VECTOR_REG"))
        source_citations = cits
        if rows:
            return attach_source_errors(
                {"regulations": rows[:top], "citations": [c.__dict__ for c in cits]},
                source_citations,
            )
    # Fallback: provide applicable regulation citations
    return attach_source_errors({
        "query": query[:80],
        "regulations": [],
        "status": "no_data_fallback",
        "no_data_guidance": (
            "No regulation documents found for this query. Use the regulation references below "
            "to identify applicable rules and provide compliance guidance."
        ),
        "regulation_references": REGULATORY_REFERENCES,
    }, source_citations)
