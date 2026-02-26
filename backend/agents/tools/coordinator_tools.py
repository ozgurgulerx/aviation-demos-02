"""Coordinator tools — scoring, ranking, plan generation."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog

logger = structlog.get_logger()


@ai_function(approval_mode="never_require")
async def score_recovery_option(
    option_id: Annotated[str, Field(description="Unique option identifier")],
    description: Annotated[str, Field(description="Description of the recovery option")],
    delay_reduction: Annotated[float, Field(description="Score 0-100 for delay reduction")] = 50,
    crew_margin: Annotated[float, Field(description="Score 0-100 for crew duty margin")] = 50,
    safety_score: Annotated[float, Field(description="Score 0-100 for safety compliance")] = 80,
    cost_impact: Annotated[float, Field(description="Score 0-100 for cost efficiency")] = 50,
    passenger_impact: Annotated[float, Field(description="Score 0-100 for passenger impact")] = 50,
) -> Dict[str, Any]:
    """Score a recovery option across multiple objectives."""
    scores = {
        "delay_reduction": delay_reduction,
        "crew_margin": crew_margin,
        "safety_score": safety_score,
        "cost_impact": cost_impact,
        "passenger_impact": passenger_impact,
    }
    weights = {"delay_reduction": 0.25, "crew_margin": 0.15, "safety_score": 0.25, "cost_impact": 0.15, "passenger_impact": 0.20}
    overall = sum(scores[k] * weights[k] for k in scores)
    return {
        "option_id": option_id,
        "description": description,
        "scores": scores,
        "overall_score": round(overall, 1),
    }


@ai_function(approval_mode="never_require")
async def rank_options(
    options: Annotated[List[Dict[str, Any]], Field(description="List of scored options")],
) -> Dict[str, Any]:
    """Rank recovery options by overall score."""
    sorted_opts = sorted(options, key=lambda o: o.get("overall_score", 0), reverse=True)
    for i, opt in enumerate(sorted_opts):
        opt["rank"] = i + 1
    return {"ranked_options": sorted_opts, "top_option": sorted_opts[0] if sorted_opts else None}


@ai_function(approval_mode="never_require")
async def generate_plan(
    selected_option: Annotated[Dict[str, Any], Field(description="The selected recovery option")],
    timeline_entries: Annotated[List[Dict[str, str]], Field(description="Timeline entries [{time, action, agent}]")] = None,
) -> Dict[str, Any]:
    """Generate an implementation plan for the selected recovery option."""
    return {
        "selected_option": selected_option,
        "timeline": timeline_entries or [
            {"time": "T+0", "action": "Initiate recovery plan", "agent": "coordinator"},
            {"time": "T+15min", "action": "Begin aircraft swaps", "agent": "fleet_recovery"},
            {"time": "T+30min", "action": "Reassign crew", "agent": "crew_recovery"},
            {"time": "T+45min", "action": "Rebook affected passengers", "agent": "passenger_impact"},
            {"time": "T+60min", "action": "Monitor execution", "agent": "situation_assessment"},
        ],
        "status": "plan_generated",
    }
