"""
Workflow definitions using Microsoft Agent Framework patterns.
Implements sequential and LLM-driven handoff orchestration for aviation domain.
"""

from typing import Dict, List, Optional

from agent_framework import (
    ChatAgent,
    ChatMessage,
    Workflow,
    SequentialBuilder,
    HandoffBuilder,
    WorkflowBuilder,
    Executor,
    handler,
    WorkflowContext,
    AgentExecutorResponse,
)
import structlog

from orchestrator.agent_registry import (
    SCENARIO_AGENTS,
    detect_scenario,
    get_agent_by_id,
)
from agents.middleware import ToolCallSanitizer

logger = structlog.get_logger()

TERMINATION_RECOMMENDATION_KEYWORDS = {
    "recommend", "final", "suggest", "propose", "conclusion",
    "decision", "advise", "our plan",
}
TERMINATION_TIMELINE_KEYWORDS = {
    "timeline", "implementation", "summary", "plan", "schedule",
    "next steps", "action items",
}


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

_sanitizer = ToolCallSanitizer()


def _create_agent_by_id(agent_id: str) -> Optional[ChatAgent]:
    """Create a ChatAgent instance from the agent registry."""
    from agents import agent_factories
    factory = agent_factories.get(agent_id)
    if not factory:
        logger.warning("agent_factory_not_found", agent_id=agent_id)
        return None
    try:
        agent = factory(name=agent_id)
        # Attach ToolCallSanitizer so orphaned tool_calls in conversation
        # history are patched before reaching Azure OpenAI.
        agent.middleware = list(agent.middleware or []) + [_sanitizer]
        return agent
    except Exception as e:
        logger.error("agent_factory_failed", agent_id=agent_id, error=str(e))
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
    problem: str = "",
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
        from agents import create_decision_coordinator
        coordinator = create_decision_coordinator(name="coordinator_fallback")

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

    scenario_context = ""
    if problem:
        scenario_context = (
            f"\n## Current Scenario\n{problem}\n\n"
            "Use these specific details (airports, flight counts, passenger numbers, "
            "aircraft grounded) when calling your tools and in your analysis. "
            "Tailor everything to this scenario — do not produce generic assessments.\n"
        )

    coordinator_instructions = f"""You are the Aviation Decision Coordinator for a {scenario.replace('_', ' ')} scenario.
{scenario_context}
## Phase 1 — Delegate (ONE round only)
Call each specialist handoff tool EXACTLY ONCE, in order:
{handoff_directives}

IMPORTANT: Do NOT call the same specialist twice. Once you have heard back from
ALL {len(specialists)} specialists, move to Phase 2.

## Phase 2 — Synthesize
After all specialists have reported back:
1. Summarize findings from each specialist
2. Score 3-5 recovery options using score_recovery_option
3. Rank them using rank_options
4. Generate implementation plan using generate_plan
5. Provide a clear "Final Answer" that directly answers the user's original query in plain language.
6. End with a JSON block that follows this schema exactly:
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
  "finalAnswer": "plain-language answer to the original user query",
  "timeline": [{{"time": "T+0", "action": "action text", "agent": "agent_id"}}]
}}

You are DONE after Phase 2. Do not delegate again.

## Empty/No-Data Rule
If specialists return no data, empty results, or zero query matches, do NOT
re-delegate. Instead, synthesize recommendations based on aviation domain
knowledge, standard operating procedures, and the scenario context.
State clearly which recommendations are data-backed vs. SOP-based.

Start now by calling the first handoff tool.
"""
    coordinator.default_options["instructions"] = coordinator_instructions

    coordinator_ref = coordinator.name or coordinator.id
    for specialist in specialists:
        specialist_base = specialist.default_options.get("instructions") or ""
        handoff_protocol = (
            "Workflow protocol — FOLLOW THESE STEPS IN ORDER:\n"
            "Step 1: Call your analysis tools to gather data.\n"
            "Step 2: Write a DETAILED analysis (minimum 3 paragraphs) interpreting results.\n"
            "  - If tools returned data: cite specific numbers, flag risks, give recommendations.\n"
            "  - If tools returned 'no_data_fallback': apply the domain-knowledge constants and\n"
            "    scenario context to produce a substantive, scenario-specific assessment.\n"
            "  IMPORTANT: You MUST write your full analysis as text output BEFORE Step 3.\n"
            "  Do NOT skip writing — the coordinator needs your written findings.\n"
            f"Step 3: ONLY after writing your analysis, call `handoff_to_{coordinator_ref}`.\n"
            "Do not hand off to any other specialist.\n\n"
        )
        specialist.default_options["instructions"] = (
            f"{handoff_protocol}{scenario_context}{specialist_base}"
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
    default_coordinator_turns = len(specialists) + 6
    coordinator_turn_limit = configured_turn_limits.get(
        coordinator.name or coordinator.id, default_coordinator_turns
    )
    specialist_turn_limits = {
        (s.name or s.id): configured_turn_limits.get(s.name or s.id, 4)
        for s in specialists
    }
    turn_limits = {
        (coordinator.name or coordinator.id): max(1, int(coordinator_turn_limit)),
        **{k: max(1, int(v)) for k, v in specialist_turn_limits.items()},
    }
    builder = builder.with_autonomous_mode(turn_limits=turn_limits)

    n_specialists = len(specialists)

    def should_terminate(conversation):
        n_msgs = len(conversation)
        if n_msgs < 4:
            return False
        recent = " ".join(getattr(m, "text", "") or "" for m in conversation[-12:]).lower()
        has_recommendation = any(kw in recent for kw in TERMINATION_RECOMMENDATION_KEYWORDS)
        has_timeline = any(kw in recent for kw in TERMINATION_TIMELINE_KEYWORDS)
        has_final_tool_signal = (
            "generate_plan" in recent
            or "rank_options" in recent
            or "score_recovery_option" in recent
        )
        # Safety valve: allow enough room for all specialist handoffs + coordinator synthesis
        conversation_long_enough = n_msgs > (n_specialists * 3 + 6)
        should_stop = (
            (has_recommendation and has_timeline)
            or has_final_tool_signal
            or conversation_long_enough
        )
        if should_stop or n_msgs % 20 == 0:
            logger.info(
                "termination_check",
                n_msgs=n_msgs,
                should_stop=should_stop,
                has_recommendation=has_recommendation,
                has_timeline=has_timeline,
                has_final_tool_signal=has_final_tool_signal,
                conversation_long_enough=conversation_long_enough,
            )
        return should_stop

    builder = builder.with_termination_condition(should_terminate)

    workflow = builder.build()

    logger.info(
        "coordinator_workflow_created", name=workflow_name,
        coordinator=resolved_coordinator_id, specialist_count=len(specialists),
    )
    return workflow


class _SpecialistAggregator(Executor):
    """Dispatches input to parallel specialists, then aggregates their responses for the coordinator."""

    def __init__(self, coordinator_executor_id: str, specialist_ids: List[str], **kwargs):
        super().__init__(**kwargs)
        self._coordinator_executor_id = coordinator_executor_id
        self._specialist_ids = specialist_ids

    @handler
    async def dispatch(self, message: str, ctx: WorkflowContext) -> None:
        """Handle initial string input — fan-out to all specialists."""
        for sid in self._specialist_ids:
            await ctx.send_message(message, target_id=sid)

    @handler
    async def aggregate(self, results: List[AgentExecutorResponse], ctx: WorkflowContext) -> None:
        """Handle fan-in specialist results — format and forward to coordinator."""
        parts = []
        for r in results:
            msgs = r.agent_response.messages if r.agent_response and r.agent_response.messages else []
            text = "\n".join(getattr(m, "text", "") or "" for m in msgs)
            parts.append(f"=== {r.executor_id} findings ===\n{text or '(No findings returned)'}")
        summary = (
            "All specialist analyses are complete. Here are the specialist findings:\n\n"
            + "\n\n".join(parts)
            + "\n\nPlease synthesize a final decision."
        )
        msg = ChatMessage(role="user", text=summary)
        await ctx.send_message([msg], target_id=self._coordinator_executor_id)


def create_deterministic_coordinator_workflow(
    scenario: str,
    active_agent_ids: List[str],
    coordinator_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Workflow:
    """
    Create a deterministic coordinator workflow.
    Specialists execute concurrently in parallel, then coordinator synthesizes final output.
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
        from agents import create_decision_coordinator
        coordinator = create_decision_coordinator(name="coordinator_fallback")

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
4) Provide a clear "Final Answer" that directly answers the user's original query in plain language.
5) End with a JSON block that follows this schema exactly:
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
  "finalAnswer": "plain-language answer to the original user query",
  "timeline": [{{"time": "T+0", "action": "action text", "agent": "agent_id"}}]
}}
"""

    # Build parallel specialist → coordinator workflow
    coordinator_exec_id = resolved_coordinator_id
    aggregator_id = "specialist_aggregator"
    builder = WorkflowBuilder(name=workflow_name)

    specialist_refs = []
    for specialist in specialists:
        sid = specialist.name or specialist.id
        s = specialist  # capture for lambda
        builder.register_agent(lambda _s=s: _s, name=sid)
        specialist_refs.append(sid)
    builder.register_agent(lambda: coordinator, name=coordinator_exec_id, output_response=True)
    # Capture specialist_refs for the lambda
    _srefs = list(specialist_refs)
    builder.register_executor(
        lambda: _SpecialistAggregator(
            id=aggregator_id,
            coordinator_executor_id=coordinator_exec_id,
            specialist_ids=_srefs,
        ),
        name=aggregator_id,
    )
    builder.set_start_executor(aggregator_id)

    # Fan-out: aggregator dispatches to all specialists in parallel
    builder.add_fan_out_edges(aggregator_id, specialist_refs)
    # Fan-in: specialist results flow back to aggregator for formatting
    builder.add_fan_in_edges(specialist_refs, aggregator_id)
    # Chain: aggregator sends formatted summary to coordinator
    builder.add_edge(aggregator_id, coordinator_exec_id)

    workflow = builder.build()

    logger.info(
        "deterministic_coordinator_workflow_created",
        name=workflow_name,
        coordinator=resolved_coordinator_id,
        specialist_count=len(specialists),
        parallel=True,
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
        if mode == OrchestrationMode.LLM_DIRECTED:
            return create_coordinator_workflow(
                scenario=scenario,
                active_agent_ids=active_ids,
                coordinator_id=coordinator_id,
                autonomous_turn_limits=autonomous_turn_limits,
                name=name or f"handoff_{scenario}",
                problem=problem,
            )
        if mode == OrchestrationMode.DETERMINISTIC:
            return create_deterministic_coordinator_workflow(
                scenario=scenario,
                active_agent_ids=active_ids,
                coordinator_id=coordinator_id,
                name=name or f"handoff_{scenario}",
            )
        raise ValueError(f"Unknown orchestration mode: {mode}")

    else:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
