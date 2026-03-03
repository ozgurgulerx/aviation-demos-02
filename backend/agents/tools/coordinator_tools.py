"""Coordinator tools — scoring, ranking, plan generation."""

from typing import Annotated, Any, Dict, List
from agent_framework import tool as ai_function
from pydantic import Field
import structlog

logger = structlog.get_logger()


def _flatten_option_candidates(value: Any) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []

    def _walk(item: Any):
        if isinstance(item, dict):
            flattened.append(dict(item))
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                _walk(child)

    _walk(value)
    return flattened


def _normalize_selected_option(selected_option: Any) -> Dict[str, Any]:
    if isinstance(selected_option, dict):
        return dict(selected_option)
    if isinstance(selected_option, list):
        for item in selected_option:
            if isinstance(item, dict):
                return dict(item)
    return {}


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
    candidates = _flatten_option_candidates(options)
    if not candidates:
        return {
            "ranked_options": [],
            "top_option": None,
            "status": "invalid_options_shape",
            "errorCode": "coordinator_options_invalid_shape",
            "message": "No valid option objects were provided to rank_options.",
        }

    def _score(option: Dict[str, Any]) -> float:
        for key in ("overall_score", "overallScore", "score"):
            try:
                if key in option and option[key] is not None:
                    return float(option[key])
            except (TypeError, ValueError):
                pass
        return 0.0

    sorted_opts = sorted(candidates, key=_score, reverse=True)
    for i, opt in enumerate(sorted_opts):
        opt["rank"] = i + 1
    return {"ranked_options": sorted_opts, "top_option": sorted_opts[0] if sorted_opts else None}


@ai_function(approval_mode="never_require")
async def generate_plan(
    selected_option: Annotated[Any, Field(description="The selected recovery option")],
    timeline_entries: Annotated[List[Dict[str, str]], Field(description="Timeline entries [{time, action, agent}]")] = None,
) -> Dict[str, Any]:
    """Generate an implementation plan for the selected recovery option."""
    normalized_selected_option = _normalize_selected_option(selected_option)
    if not normalized_selected_option:
        return {
            "selected_option": {},
            "timeline": [],
            "status": "invalid_selected_option_shape",
            "errorCode": "coordinator_options_invalid_shape",
            "message": "No valid selected option object was provided to generate_plan.",
        }

    normalized_timeline: List[Dict[str, str]] = []
    if isinstance(timeline_entries, list):
        for entry in timeline_entries:
            if not isinstance(entry, dict):
                continue
            normalized_timeline.append(
                {
                    "time": str(entry.get("time") or ""),
                    "action": str(entry.get("action") or ""),
                    "agent": str(entry.get("agent") or ""),
                }
            )

    return {
        "selected_option": normalized_selected_option,
        "timeline": normalized_timeline or [
            {"time": "T+0", "action": "Initiate recovery plan", "agent": "coordinator"},
            {"time": "T+15min", "action": "Begin aircraft swaps", "agent": "fleet_recovery"},
            {"time": "T+30min", "action": "Reassign crew", "agent": "crew_recovery"},
            {"time": "T+45min", "action": "Rebook affected passengers", "agent": "passenger_impact"},
            {"time": "T+60min", "action": "Monitor execution", "agent": "situation_assessment"},
        ],
        "status": "plan_generated",
    }
