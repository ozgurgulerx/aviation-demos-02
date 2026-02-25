"""
Workflow definitions using Microsoft Agent Framework patterns.
Implements sequential and LLM-driven handoff orchestration for aviation domain.
"""

from typing import List, Optional

from agent_framework import (
    ChatAgent,
    Workflow,
    SequentialBuilder,
    HandoffBuilder,
    ChatMessage,
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
    coordinator_id = scenario_config["coordinator"]

    # Build coordinator agent with orchestrator-tier model
    coordinator = _create_agent_by_id(coordinator_id)
    if not coordinator:
        # Fallback
        from agents import create_flight_analyst
        coordinator = create_flight_analyst(name="coordinator_fallback")

    # Build specialist agents
    specialists: List[ChatAgent] = []
    for agent_id in active_agent_ids:
        if agent_id == coordinator_id:
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
    coordinator._instructions = coordinator_instructions

    # Build handoff workflow
    all_participants = [coordinator] + specialists
    builder = HandoffBuilder(
        name=workflow_name,
        participants=all_participants,
    ).with_start_agent(coordinator)

    builder = builder.with_autonomous_mode()

    def should_terminate(conversation):
        if len(conversation) < 6:
            return False
        recent = " ".join(getattr(m, "text", "") or "" for m in conversation[-5:]).lower()
        return ("recommend" in recent or "implementation" in recent) and len(conversation) > 12

    builder = builder.with_termination_condition(should_terminate)

    workflow = builder.build()

    logger.info(
        "coordinator_workflow_created", name=workflow_name,
        coordinator=coordinator_id, specialist_count=len(specialists),
    )
    return workflow


# ═══════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════

def create_workflow(
    workflow_type: str,
    name: Optional[str] = None,
    problem: str = "",
    **kwargs,
) -> Workflow:
    """Factory function to create workflows of different types."""
    logger.info("creating_workflow", workflow_type=workflow_type, name=name)

    if workflow_type == WorkflowType.SEQUENTIAL:
        return create_sequential_workflow(name=name or "sequential_workflow")

    elif workflow_type == WorkflowType.HANDOFF:
        scenario = detect_scenario(problem)
        scenario_config = SCENARIO_AGENTS.get(scenario, SCENARIO_AGENTS["hub_disruption"])
        active_ids = scenario_config["agents"] + [scenario_config["coordinator"]]
        return create_coordinator_workflow(
            scenario=scenario,
            active_agent_ids=active_ids,
            name=name or f"handoff_{scenario}",
        )

    else:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
