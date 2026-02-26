"""
Workflow definitions using Microsoft Agent Framework patterns.
Implements sequential and LLM-driven handoff orchestration for aviation domain.
"""

from typing import Dict, List, Optional

from agent_framework import (
    ChatAgent,
    Workflow,
    SequentialBuilder,
    HandoffBuilder,
)
import structlog

from orchestrator.agent_registry import (
    SCENARIO_AGENTS,
    detect_scenario,
    get_agent_by_id,
)

logger = structlog.get_logger()


class WorkflowType:
    SEQUENTIAL = "sequential"
    HANDOFF = "handoff"


class OrchestrationMode:
    LLM_DIRECTED = "llm_directed"
    DETERMINISTIC = "deterministic"
    HANDOFF_MESH = "handoff_mesh"


# ═══════════════════════════════════════════════════════════════════
# Agent factory — creates ChatAgent instances from registry IDs
# ═══════════════════════════════════════════════════════════════════

def _create_agent_by_id(agent_id: str) -> Optional[ChatAgent]:
    """Create a ChatAgent instance from the agent registry."""
    from agents import agent_factories
    factory = agent_factories.get(agent_id)
    if factory:
        return factory(name=agent_id)
    return None


# ═══════════════════════════════════════════════════════════════════
# Sequential workflow (legacy — FlightAnalyst → OpsAdvisor → Safety)
# ═══════════════════════════════════════════════════════════════════

def create_sequential_workflow(name: str = "sequential_aviation_solver") -> Workflow:
    """Legacy sequential: FlightAnalyst -> OperationsAdvisor -> SafetyInspector."""
    logger.info("creating_sequential_workflow", name=name)

    from agents import create_flight_analyst, create_operations_advisor, create_safety_inspector

    workflow = (
        SequentialBuilder()
        .participants([
            create_flight_analyst(name="flight_analyst"),
            create_operations_advisor(name="operations_advisor"),
            create_safety_inspector(name="safety_inspector"),
        ])
        .build()
    )
    logger.info("sequential_workflow_created", name=name, participant_count=3)
    return workflow


# ═══════════════════════════════════════════════════════════════════
# LLM-driven handoff workflow (coordinator dynamically delegates)
# ═══════════════════════════════════════════════════════════════════

def create_coordinator_workflow(
    scenario: str,
    active_agent_ids: List[str],
    coordinator_id: Optional[str] = None,
    autonomous_turn_limits: Optional[Dict[str, int]] = None,
    name: Optional[str] = None,
) -> Workflow:
    """
    Create an LLM-driven handoff workflow.
    The coordinator analyzes the problem and dynamically delegates to specialists.
    HandoffBuilder generates handoff tools so the coordinator can transfer control.
    """
    workflow_name = name or f"{scenario}_workflow"
    logger.info("creating_coordinator_workflow", name=workflow_name, scenario=scenario, agents=active_agent_ids)

    # Determine coordinator ID
    scenario_config = SCENARIO_AGENTS.get(scenario, SCENARIO_AGENTS["hub_disruption"])
    resolved_coordinator_id = coordinator_id
    if not resolved_coordinator_id:
        for agent_id in active_agent_ids:
            agent_def = get_agent_by_id(agent_id)
            if agent_def and agent_def.category == "coordinator":
                resolved_coordinator_id = agent_id
                break
    if not resolved_coordinator_id:
        resolved_coordinator_id = scenario_config["coordinator"]

    # Build coordinator agent with orchestrator-tier model
    coordinator = _create_agent_by_id(resolved_coordinator_id)
    if not coordinator:
        # Fallback
        from agents import create_flight_analyst
        coordinator = create_flight_analyst(name="coordinator_fallback")

    # Build specialist agents
    specialists: List[ChatAgent] = []
    for agent_id in active_agent_ids:
        if agent_id == resolved_coordinator_id:
            continue
        agent = _create_agent_by_id(agent_id)
        if agent:
            specialists.append(agent)

    if not specialists:
        logger.warning("no_specialists_created", scenario=scenario)
        return create_sequential_workflow()

    # Build explicit handoff directives with actual tool names
    handoff_directives = "\n".join(
        f"- Call `handoff_to_{s.name}` → {getattr(s, 'description', 'specialist agent')}"
        for s in specialists
    )

    coordinator_instructions = f"""You are the Aviation Decision Coordinator for a {scenario.replace('_', ' ')} scenario.

You MUST delegate analysis to specialists by calling the handoff tools below.
DO NOT analyze the problem yourself first — hand off to specialists immediately.

## Handoff Tools (call these in order):
{handoff_directives}

## Process:
1. Call each handoff tool above to delegate to that specialist
2. After ALL specialists have reported back, synthesize their findings
3. Score recovery options using your scoring tools
4. Output ranked options with your recommendation

Start by calling the first handoff tool now.
"""
    coordinator.default_options["instructions"] = coordinator_instructions
    coordinator_ref = coordinator.name or coordinator.id
    for specialist in specialists:
        specialist_base = specialist.default_options.get("instructions") or ""
        specialist.default_options["instructions"] = (
            f"{specialist_base}\n\n"
            "Workflow protocol:\n"
            "- Run one focused analysis pass using your tools.\n"
            "- Return concise, evidence-backed findings.\n"
            f"- Immediately call `handoff_to_{coordinator_ref}` after your findings.\n"
            "- Do not hand off to any other specialist.\n"
        )

    # Build handoff workflow
    all_participants = [coordinator] + specialists
    builder = HandoffBuilder(
        name=workflow_name,
        participants=all_participants,
    ).with_start_agent(coordinator)

    # Explicit routing: coordinator <-> specialists (no specialist-to-specialist mesh).
    builder = builder.add_handoff(coordinator, specialists)
    for specialist in specialists:
        builder = builder.add_handoff(specialist, [coordinator])

    configured_turn_limits = autonomous_turn_limits or {}
    coordinator_turn_limit = configured_turn_limits.get(coordinator.name or coordinator.id, 8)
    specialist_turn_limits = {
        (s.name or s.id): configured_turn_limits.get(s.name or s.id, 2)
        for s in specialists
    }
    turn_limits = {
        (coordinator.name or coordinator.id): max(1, int(coordinator_turn_limit)),
        **{k: max(1, int(v)) for k, v in specialist_turn_limits.items()},
    }
    builder = builder.with_autonomous_mode(turn_limits=turn_limits)

    def should_terminate(conversation):
        if len(conversation) < 6:
            return False
        recent = " ".join(getattr(m, "text", "") or "" for m in conversation[-8:]).lower()
        has_recommendation = "recommend" in recent
        has_timeline = "timeline" in recent or "implementation" in recent
        has_final_tool_signal = (
            "generate_plan" in recent
            or "rank_options" in recent
            or "score_recovery_option" in recent
        )
        return (has_recommendation and has_timeline) or has_final_tool_signal

    builder = builder.with_termination_condition(should_terminate)

    workflow = builder.build()

    logger.info(
        "coordinator_workflow_created", name=workflow_name,
        coordinator=resolved_coordinator_id, specialist_count=len(specialists),
    )
    return workflow


def create_deterministic_coordinator_workflow(
    scenario: str,
    active_agent_ids: List[str],
    coordinator_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Workflow:
    """
    Create a deterministic coordinator workflow.
    Specialists execute once in scenario order, then coordinator synthesizes final output.
    """
    workflow_name = name or f"{scenario}_deterministic_workflow"
    logger.info(
        "creating_deterministic_coordinator_workflow",
        name=workflow_name,
        scenario=scenario,
        agents=active_agent_ids,
    )

    scenario_config = SCENARIO_AGENTS.get(scenario, SCENARIO_AGENTS["hub_disruption"])
    resolved_coordinator_id = coordinator_id
    if not resolved_coordinator_id:
        for agent_id in active_agent_ids:
            agent_def = get_agent_by_id(agent_id)
            if agent_def and agent_def.category == "coordinator":
                resolved_coordinator_id = agent_id
                break
    if not resolved_coordinator_id:
        resolved_coordinator_id = scenario_config["coordinator"]
    active_id_set = set(active_agent_ids)

    coordinator = _create_agent_by_id(resolved_coordinator_id)
    if not coordinator:
        from agents import create_flight_analyst
        coordinator = create_flight_analyst(name="coordinator_fallback")

    specialists: List[ChatAgent] = []
    for agent_id in active_agent_ids:
        if agent_id == resolved_coordinator_id or agent_id not in active_id_set:
            continue
        agent = _create_agent_by_id(agent_id)
        if agent:
            specialists.append(agent)

    if not specialists:
        logger.warning("no_specialists_created_deterministic", scenario=scenario)
        participants = [coordinator]
        workflow = SequentialBuilder().participants(participants).build()
        logger.info(
            "deterministic_coordinator_workflow_created",
            name=workflow_name,
            coordinator=resolved_coordinator_id,
            specialist_count=0,
        )
        return workflow

    coordinator.default_options["instructions"] = f"""You are the Aviation Decision Coordinator for a {scenario.replace('_', ' ')} scenario.

You are running in bounded orchestration mode. Specialists have already executed.
Your job is to synthesize their findings into a final decision using your scoring and planning tools.

Requirements:
1) Score recovery/decision options with explicit criteria.
2) Provide ranked options and select one recommendation.
3) Provide an implementation timeline.
4) End with a JSON block that follows this schema exactly:
{{
  "criteria": ["delay_reduction", "crew_margin", "safety_score", "cost_impact", "passenger_impact"],
  "options": [
    {{
      "optionId": "opt-1",
      "description": "short description",
      "rank": 1,
      "scores": {{
        "delay_reduction": 0,
        "crew_margin": 0,
        "safety_score": 0,
        "cost_impact": 0,
        "passenger_impact": 0
      }}
    }}
  ],
  "selectedOptionId": "opt-1",
  "summary": "brief recommendation summary",
  "timeline": [{{"time": "T+0", "action": "action text", "agent": "agent_id"}}]
}}
"""

    participants = [*specialists, coordinator]
    workflow = SequentialBuilder().participants(participants).build()
    logger.info(
        "deterministic_coordinator_workflow_created",
        name=workflow_name,
        coordinator=resolved_coordinator_id,
        specialist_count=len(specialists),
    )
    return workflow


# ═══════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════

def create_workflow(
    workflow_type: str,
    name: Optional[str] = None,
    problem: str = "",
    active_agent_ids: Optional[List[str]] = None,
    coordinator_id: Optional[str] = None,
    autonomous_turn_limits: Optional[Dict[str, int]] = None,
    orchestration_mode: Optional[str] = None,
    **kwargs,
) -> Workflow:
    """Factory function to create workflows of different types."""
    logger.info("creating_workflow", workflow_type=workflow_type, name=name)

    if workflow_type == WorkflowType.SEQUENTIAL:
        return create_sequential_workflow(name=name or "sequential_workflow")

    elif workflow_type == WorkflowType.HANDOFF:
        scenario = detect_scenario(problem)
        scenario_config = SCENARIO_AGENTS.get(scenario, SCENARIO_AGENTS["hub_disruption"])
        active_ids = active_agent_ids or (scenario_config["agents"] + [scenario_config["coordinator"]])
        mode = orchestration_mode or OrchestrationMode.LLM_DIRECTED
        if mode == OrchestrationMode.HANDOFF_MESH:
            return create_coordinator_workflow(
                scenario=scenario,
                active_agent_ids=active_ids,
                coordinator_id=coordinator_id,
                autonomous_turn_limits=autonomous_turn_limits,
                name=name or f"handoff_{scenario}",
            )
        if mode in {OrchestrationMode.DETERMINISTIC, OrchestrationMode.LLM_DIRECTED}:
            return create_deterministic_coordinator_workflow(
                scenario=scenario,
                active_agent_ids=active_ids,
                coordinator_id=coordinator_id,
                name=name or f"handoff_{scenario}",
            )
        raise ValueError(f"Unknown orchestration mode: {mode}")

    else:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
