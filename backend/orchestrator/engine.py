"""
Central orchestrator engine for aviation multi-agent problem solving.
Uses Microsoft Agent Framework workflow patterns for orchestration.

Supports:
- Sequential: Linear agent execution (legacy 3-agent)
- Handoff: LLM-driven coordinator delegation to dynamic specialist subsets
"""

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from openai import APIStatusError, RateLimitError, AuthenticationError

from agents.client import clear_client_cache
from agent_framework import (
    Workflow,
    WorkflowEvent,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
    WorkflowOutputEvent,
    WorkflowFailedEvent,
    ExecutorInvokedEvent,
    ExecutorCompletedEvent,
    AgentRunEvent,
    AgentRunUpdateEvent,
    InMemoryCheckpointStorage,
)
from pydantic import BaseModel, Field
import structlog

from orchestrator.workflows import OrchestrationMode, WorkflowType, create_workflow
from orchestrator.middleware import EvidenceCollector
from orchestrator.agent_registry import (
    SCENARIO_AGENTS,
    get_agent_by_id,
    select_agents_for_problem,
    detect_scenario,
    AgentSelectionResult,
)
from orchestrator.trace_emitter import TraceEmitter
from telemetry import get_tracer, traced_span
from data_sources.azure_client import get_shared_async_client
from data_sources.shared_utils import OPENAI_API_VERSION, supports_explicit_temperature

logger = structlog.get_logger()

_tracer = get_tracer("orchestrator")
DEFAULT_RECOVERY_CRITERIA = [
    "delay_reduction",
    "crew_margin",
    "safety_score",
    "cost_impact",
    "passenger_impact",
]


class _LoopCappedSignal(Exception):
    """Raised when LLM-directed loop guard caps invocations gracefully."""
    pass


class OrchestratorDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision_type: str
    reasoning: str
    confidence: float = Field(default=0.9, ge=0, le=1)
    action: Dict[str, Any] = Field(default_factory=dict)


class OrchestratorEngine:
    """
    Central orchestrator using Microsoft Agent Framework workflow patterns.
    Now supports 20-agent registry with scenario detection and LLM-driven handoff.
    """

    def __init__(
        self,
        run_id: str,
        event_emitter: Optional[Callable] = None,
        workflow_type: str = WorkflowType.HANDOFF,
        orchestration_mode: Optional[str] = None,
        enable_checkpointing: bool = True,
        max_executor_invocations: Optional[int] = None,
        autonomous_turn_limits: Optional[Dict[str, int]] = None,
    ):
        self.run_id = run_id
        self.event_emitter = event_emitter
        self.workflow_type = workflow_type
        self.orchestration_mode = self._resolve_orchestration_mode(
            workflow_type=workflow_type,
            orchestration_mode=orchestration_mode,
        )
        self.enable_checkpointing = enable_checkpointing
        self.evidence_collector = EvidenceCollector()
        self.workflow: Optional[Workflow] = None
        self.decisions: List[OrchestratorDecision] = []
        self.evidence: List[Dict[str, Any]] = []
        self._decision_counter = 0

        self.trace_emitter: Optional[TraceEmitter] = None
        self.selected_agents: List[AgentSelectionResult] = []
        self.excluded_agents: List[AgentSelectionResult] = []
        self.scenario: str = "hub_disruption"
        self._agent_lookup: Dict[str, AgentSelectionResult] = {}
        self._active_query_contexts: Dict[str, Dict[str, Any]] = {}
        self._last_executor_id: Optional[str] = None
        self._run_started_at = datetime.now(timezone.utc)
        self._current_step = "initializing"
        self._completed_phases: set[str] = set()
        self._agent_started_at: Dict[str, datetime] = {}
        self._agent_progress_pct: Dict[str, float] = {}
        self._active_agent_ids: set[str] = set()
        self._completed_agent_ids: set[str] = set()
        self._failed_agent_ids: set[str] = set()
        self._activated_agent_ids: set[str] = set()
        self._agent_execution_counts: Dict[str, int] = {}
        self._executor_invocations_total: int = 0
        self._max_executor_invocations_override = max_executor_invocations
        self._max_executor_invocations_effective: int = 0
        self._loop_guard_reason: Optional[str] = None
        self._autonomous_turn_limits = autonomous_turn_limits or {}
        self._deterministic_execution_timeout_seconds = int(
            os.getenv("DETERMINISTIC_EXECUTION_TIMEOUT_SECONDS", "600")
        )
        self._coordinator_agent_id: Optional[str] = None
        self._coordinator_artifacts_emitted = False

        if enable_checkpointing:
            self.checkpoint_storage = InMemoryCheckpointStorage()
        else:
            self.checkpoint_storage = None

        logger.info(
            "orchestrator_initialized",
            run_id=run_id,
            workflow_type=workflow_type,
            orchestration_mode=self.orchestration_mode,
        )

    @staticmethod
    def _resolve_orchestration_mode(workflow_type: str, orchestration_mode: Optional[str]) -> Optional[str]:
        if workflow_type != WorkflowType.HANDOFF:
            return orchestration_mode
        if orchestration_mode:
            return orchestration_mode
        return OrchestrationMode.LLM_DIRECTED

    def _is_deterministic_mode(self) -> bool:
        return (
            self.workflow_type == WorkflowType.HANDOFF
            and self.orchestration_mode == OrchestrationMode.DETERMINISTIC
        )

    def _is_llm_directed_mode(self) -> bool:
        return (
            self.workflow_type == WorkflowType.HANDOFF
            and self.orchestration_mode == OrchestrationMode.LLM_DIRECTED
        )

    def _is_bounded_orchestration_mode(self) -> bool:
        return (
            self.workflow_type == WorkflowType.HANDOFF
            and self.orchestration_mode in {OrchestrationMode.DETERMINISTIC, OrchestrationMode.LLM_DIRECTED}
        )

    async def emit_event(self, event_type: str, payload: Dict[str, Any]):
        if self.event_emitter:
            actor = payload.get("actor")
            if not isinstance(actor, dict):
                agent_id = payload.get("agentId") or payload.get("agent_id") or payload.get("executor_id")
                agent_name = payload.get("agentName") or payload.get("agent_name") or payload.get("executor_name")
                if agent_id:
                    actor = {"kind": "agent", "id": agent_id, "name": agent_name or agent_id}
                else:
                    actor = {"kind": "orchestrator", "id": "orchestrator", "name": "Orchestrator"}
            full_payload = {
                "run_id": self.run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                **payload,
            }
            await self.event_emitter(event_type=event_type, payload=full_payload)

    def _record_decision(self, decision_type: str, reasoning: str, confidence: float = 0.9, action: Dict[str, Any] = None) -> OrchestratorDecision:
        self._decision_counter += 1
        decision = OrchestratorDecision(
            decision_type=decision_type, reasoning=reasoning,
            confidence=confidence, action=action or {},
        )
        self.decisions.append(decision)
        logger.info("orchestrator_decision", decision_id=decision.decision_id, decision_type=decision_type, reasoning=reasoning[:100])
        return decision

    def _progress_payload(self, current_step: str) -> Dict[str, Any]:
        agent_total = len(self.selected_agents)
        completion_ratio = (
            len(self._completed_agent_ids) / max(agent_total, 1)
            if agent_total > 0
            else 0.0
        )
        phase_weights = {
            "select_agents": 0.10,
            "activate_agents": 0.12,
            "create_workflow": 0.12,
            "execute_workflow": 0.56,
            "synthesize_output": 0.10,
        }

        base_without_execute = 0.0
        for phase, weight in phase_weights.items():
            if phase == "execute_workflow":
                continue
            if phase in self._completed_phases:
                base_without_execute += weight
        if "execute_workflow" in self._completed_phases:
            execute_component = phase_weights["execute_workflow"]
        else:
            execute_component = phase_weights["execute_workflow"] * completion_ratio

        run_progress_pct = round(min(base_without_execute + execute_component, 1.0) * 100, 2)

        return {
            "runProgressPct": run_progress_pct,
            "agentsTotal": agent_total,
            "agentsActivated": len(self._activated_agent_ids),
            "agentsRunning": len(self._active_agent_ids),
            "agentsDone": len(self._completed_agent_ids),
            "agentsErrored": len(self._failed_agent_ids),
            "executorInvocations": self._executor_invocations_total,
            "maxExecutorInvocations": self._max_executor_invocations_effective,
            "currentStep": current_step,
        }

    async def _emit_progress(self, current_step: str):
        self._current_step = current_step
        await self.emit_event(
            "progress_update",
            self._progress_payload(current_step=current_step),
        )

    async def _emit_stage_started(self, stage_id: str, stage_name: str):
        await self.emit_event(
            "stage_started",
            {
                "stage_id": stage_id,
                "stage_name": stage_name,
                **self._progress_payload(current_step=stage_id),
            },
        )

    async def _emit_stage_completed(self, stage_id: str, stage_name: str, started_at: datetime):
        duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        self._completed_phases.add(stage_id)
        await self.emit_event(
            "stage_completed",
            {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "durationMs": duration_ms,
                "duration_ms": duration_ms,
                **self._progress_payload(current_step=stage_id),
            },
        )

    def get_agent_metadata(self) -> List[Dict[str, Any]]:
        """Return agent metadata for API response (for frontend canvas)."""
        agents = []
        for a in self.selected_agents:
            agents.append({
                "id": a.agent_id, "name": a.agent_name, "icon": a.icon,
                "color": a.color, "dataSources": a.data_sources,
                "included": True, "reason": a.reason,
            })
        for a in self.excluded_agents:
            agents.append({
                "id": a.agent_id, "name": a.agent_name, "icon": a.icon,
                "color": a.color, "dataSources": a.data_sources,
                "included": False, "reason": a.reason,
            })
        return agents

    async def run(self, problem: str) -> Dict[str, Any]:
        with traced_span(_tracer, "orchestrator.run"):
            return await self._run_inner(problem)

    async def _run_inner(self, problem: str) -> Dict[str, Any]:
        logger.info("orchestrator_run_started", run_id=self.run_id, workflow_type=self.workflow_type)

        self.trace_emitter = TraceEmitter(run_id=self.run_id, event_callback=self.event_emitter)

        await self.emit_event("orchestrator.run_started", {
            "workflow_type": self.workflow_type,
            "orchestration_mode": self.orchestration_mode,
            "problem_summary": problem[:200],
        })
        await self._emit_progress("run_started")

        try:
            # Phase 1: Detect scenario and select agents
            select_started_at = datetime.now(timezone.utc)
            await self._emit_stage_started("select_agents", "Select Agents")
            with traced_span(_tracer, "orchestrator.select_agents"):
                self.scenario = detect_scenario(problem)
                await self._select_agents(problem)
            await self._emit_stage_completed("select_agents", "Select Agents", select_started_at)

            # Phase 2: Emit activation events for canvas
            activate_started_at = datetime.now(timezone.utc)
            await self._emit_stage_started("activate_agents", "Activate Agents")
            await self._emit_agent_activations()
            await self._emit_stage_completed("activate_agents", "Activate Agents", activate_started_at)

            # Phase 3: Create workflow
            workflow_create_started_at = datetime.now(timezone.utc)
            await self._emit_stage_started("create_workflow", "Create Workflow")
            with traced_span(_tracer, "orchestrator.create_workflow"):
                self.workflow = await asyncio.to_thread(
                    create_workflow,
                    workflow_type=self.workflow_type,
                    name=f"{self.workflow_type}_{self.run_id}",
                    problem=problem,
                    active_agent_ids=[a.agent_id for a in self.selected_agents],
                    coordinator_id=self._coordinator_agent_id,
                    autonomous_turn_limits=self._autonomous_turn_limits,
                    orchestration_mode=self.orchestration_mode,
                )
                await self.emit_event("orchestrator.workflow_created", {
                    "workflow_type": self.workflow_type,
                    "orchestration_mode": self.orchestration_mode,
                    "scenario": self.scenario,
                })
            await self._emit_stage_completed("create_workflow", "Create Workflow", workflow_create_started_at)

            # Phase 4: Execute
            execute_started_at = datetime.now(timezone.utc)
            await self._emit_stage_started("execute_workflow", "Execute Workflow")
            n_agents = len(self.selected_agents)
            if self._is_deterministic_mode():
                # One pass through all specialists + coordinator synthesis
                default_limit = max(20, n_agents * 2)
            elif self._is_llm_directed_mode():
                # Coordinator may cycle through specialists multiple times
                default_limit = max(40, n_agents * 5)
            else:
                default_limit = max(30, n_agents * 4)
            if self._max_executor_invocations_override is not None:
                self._max_executor_invocations_effective = max(1, int(self._max_executor_invocations_override))
            else:
                self._max_executor_invocations_effective = default_limit
            input_message = self._build_workflow_input(problem)
            with traced_span(_tracer, "workflow.execute"):
                result = await self._execute_workflow_with_events(input_message)
            self._completed_phases.add("execute_workflow")
            await self._emit_stage_completed("execute_workflow", "Execute Workflow", execute_started_at)

            # Phase 5: Record completion
            synth_started_at = datetime.now(timezone.utc)
            await self._emit_stage_started("synthesize_output", "Synthesize Output")
            self._record_decision(
                decision_type="commit", reasoning="All agents completed, solution validated", confidence=0.98,
            )
            await self._emit_stage_completed("synthesize_output", "Synthesize Output", synth_started_at)

            await self.emit_event("orchestrator.run_completed", {
                "result": result, "decision_count": len(self.decisions),
                "evidence_count": len(self.evidence),
                "scenario": self.scenario,
                "orchestration_mode": self.orchestration_mode,
            })
            await self._emit_progress("run_completed")

            logger.info("orchestrator_run_completed", run_id=self.run_id, decision_count=len(self.decisions))
            return result

        except Exception as e:
            self._record_decision(
                decision_type="failure", reasoning=f"Workflow execution failed: {str(e)}",
                confidence=1.0, action={"error": str(e)},
            )
            await self.emit_event("orchestrator.run_failed", {
                "error": str(e),
                "decision_count": len(self.decisions),
                "orchestration_mode": self.orchestration_mode,
            })
            logger.error("orchestrator_run_failed", run_id=self.run_id, error=str(e))
            raise

    async def _select_agents(self, problem: str):
        self.selected_agents, self.excluded_agents = select_agents_for_problem(problem)
        scenario_config = SCENARIO_AGENTS.get(self.scenario, SCENARIO_AGENTS["hub_disruption"])
        self._coordinator_agent_id = scenario_config.get("coordinator")

        if self._is_llm_directed_mode():
            await self.emit_event(
                "workflow.status",
                {
                    "status": "llm_selection_started",
                    "message": "LLM is selecting specialist set and handoff order.",
                    "currentStep": "selecting_agents",
                },
            )
            await self._apply_llm_directed_selection(problem)

        selected_coordinator = next(
            (agent.agent_id for agent in self.selected_agents if agent.category == "coordinator"),
            None,
        )
        if selected_coordinator:
            self._coordinator_agent_id = selected_coordinator

        self._agent_lookup = {
            a.agent_id: a for a in [*self.selected_agents, *self.excluded_agents]
        }

        if self.trace_emitter:
            await self.trace_emitter.emit_plan(
                problem=problem,
                selected_agents=self.selected_agents,
                excluded_agents=self.excluded_agents,
            )

        for agent in self.selected_agents:
            if self.trace_emitter:
                await self.trace_emitter.emit_include_agent(
                    agent_id=agent.agent_id, agent_name=agent.agent_name,
                    reason=agent.reason, inputs=agent.conditions_evaluated,
                )
            self._record_decision(
                decision_type="include_agent", reasoning=agent.reason,
                action={"agent_id": agent.agent_id, "agent_name": agent.agent_name},
            )

    async def _apply_llm_directed_selection(self, problem: str):
        scenario_config = SCENARIO_AGENTS.get(self.scenario, SCENARIO_AGENTS["hub_disruption"])
        default_coordinator_id = scenario_config.get("coordinator")
        selected_baseline = {agent.agent_id for agent in self.selected_agents}
        all_profiles = [*self.selected_agents, *self.excluded_agents]
        profile_map = {profile.agent_id: profile for profile in all_profiles}
        selectable_profiles = [profile for profile in all_profiles if profile.category != "placeholder"]

        llm_plan = await self._llm_plan_agent_selection(
            problem=problem,
            selectable_profiles=selectable_profiles,
            default_coordinator_id=default_coordinator_id,
        )
        if not llm_plan:
            return

        selected_ids_raw = llm_plan.get("selectedAgentIds", [])
        execution_order_raw = llm_plan.get("executionOrder", [])
        excluded_ids_raw = llm_plan.get("excludedAgentIds", [])
        agent_reasons = llm_plan.get("agentReasons", {})
        reasoning = str(llm_plan.get("reasoning") or "LLM-directed orchestration selected agent set.")
        confidence = llm_plan.get("confidence", 0.8)
        try:
            confidence_value = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError):
            confidence_value = 0.8

        selectable_ids = {profile.agent_id for profile in selectable_profiles}
        selected_ids = [
            agent_id for agent_id in selected_ids_raw
            if isinstance(agent_id, str) and agent_id in selectable_ids
        ]
        execution_order = [
            agent_id for agent_id in execution_order_raw
            if isinstance(agent_id, str) and agent_id in selectable_ids
        ]
        excluded_ids = {
            agent_id for agent_id in excluded_ids_raw
            if isinstance(agent_id, str) and agent_id in selectable_ids
        }

        if not selected_ids:
            selected_ids = [agent.agent_id for agent in self.selected_agents if agent.agent_id in selectable_ids]
        if not selected_ids:
            selected_ids = list(selectable_ids)

        coordinator_id = str(llm_plan.get("coordinatorAgentId") or "").strip()
        coordinator_def = get_agent_by_id(coordinator_id) if coordinator_id else None
        if not coordinator_def or coordinator_def.category != "coordinator":
            coordinator_id = default_coordinator_id or ""
        if coordinator_id and coordinator_id not in selected_ids and coordinator_id in selectable_ids:
            selected_ids.append(coordinator_id)

        ordered_selected_ids: List[str] = []
        for agent_id in execution_order:
            if agent_id in selected_ids and agent_id not in ordered_selected_ids:
                ordered_selected_ids.append(agent_id)
        for agent_id in selected_ids:
            if agent_id not in ordered_selected_ids:
                ordered_selected_ids.append(agent_id)

        if coordinator_id and coordinator_id in ordered_selected_ids:
            ordered_selected_ids = [
                *[agent_id for agent_id in ordered_selected_ids if agent_id != coordinator_id],
                coordinator_id,
            ]

        selected_profiles: List[AgentSelectionResult] = []
        excluded_profiles: List[AgentSelectionResult] = []
        ordered_set = set(ordered_selected_ids)

        for agent_id in ordered_selected_ids:
            profile = profile_map.get(agent_id)
            if not profile:
                continue
            reason_suffix = str(agent_reasons.get(agent_id) or "").strip()
            reason = f"LLM-selected for this query. {reason_suffix}".strip()
            selected_profiles.append(profile.model_copy(update={"included": True, "reason": reason}))

        for profile in all_profiles:
            if profile.agent_id in ordered_set:
                continue
            was_selected = profile.agent_id in selected_baseline
            llm_excluded = profile.agent_id in excluded_ids
            reason_prefix = "LLM-excluded for this query." if llm_excluded or was_selected else profile.reason
            excluded_profiles.append(profile.model_copy(update={"included": False, "reason": reason_prefix}))

        if selected_profiles:
            self.selected_agents = selected_profiles
            self.excluded_agents = excluded_profiles
            self._coordinator_agent_id = coordinator_id or self._coordinator_agent_id
            if self.trace_emitter:
                await self.trace_emitter.emit_decision(
                    decision_type="llm_agent_selection",
                    reason=reasoning,
                    confidence=confidence_value,
                    inputs_considered=[
                        f"scenario:{self.scenario}",
                        f"selected:{','.join(agent.agent_id for agent in selected_profiles)}",
                    ],
                )

    async def _llm_plan_agent_selection(
        self,
        problem: str,
        selectable_profiles: List[AgentSelectionResult],
        default_coordinator_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not selectable_profiles:
            return None

        model = os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")
        candidate_payload = [
            {
                "agentId": profile.agent_id,
                "agentName": profile.agent_name,
                "category": profile.category,
                "priority": profile.priority,
                "dataSources": profile.data_sources,
                "defaultIncluded": profile.included,
                "defaultReason": profile.reason,
            }
            for profile in selectable_profiles
        ]
        system_prompt = (
            "You are an orchestration planner. Choose the best subset of agents and execution order for the query. "
            "Return strict JSON only with keys: selectedAgentIds, excludedAgentIds, executionOrder, "
            "coordinatorAgentId, confidence, reasoning, agentReasons. "
            "Rules: include exactly one coordinator agent and put coordinator last in executionOrder."
        )
        user_payload = {
            "problem": problem,
            "scenario": self.scenario,
            "defaultCoordinatorId": default_coordinator_id,
            "candidateAgents": candidate_payload,
        }
        request_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
            ],
        }
        if supports_explicit_temperature(model):
            request_kwargs["temperature"] = 0
        timeout_seconds = float(os.getenv("LLM_PLAN_TIMEOUT_SECONDS", "30"))

        try:
            client, _ = await get_shared_async_client(api_version=OPENAI_API_VERSION)
            response = await asyncio.wait_for(
                client.chat.completions.create(**request_kwargs),
                timeout=timeout_seconds,
            )
            raw_content = response.choices[0].message.content or ""
            parsed = self._extract_json_object_from_text(raw_content)
            if not isinstance(parsed, dict):
                logger.warning("llm_orchestration_plan_parse_failed", run_id=self.run_id, scenario=self.scenario)
                return None
            return parsed
        except asyncio.TimeoutError:
            logger.warning(
                "llm_orchestration_plan_timeout",
                run_id=self.run_id,
                scenario=self.scenario,
                timeout_seconds=timeout_seconds,
            )
            return None
        except Exception as exc:
            logger.warning(
                "llm_orchestration_plan_failed",
                run_id=self.run_id,
                scenario=self.scenario,
                error=str(exc),
            )
            return None

    async def _emit_agent_activations(self):
        """Emit agent.activated and agent.excluded events for the canvas UI."""
        if not self.trace_emitter:
            return

        for agent in self.selected_agents:
            await self.trace_emitter.emit_agent_activated(
                agent_id=agent.agent_id, agent_name=agent.agent_name,
                reason=agent.reason, data_sources=agent.data_sources,
                icon=agent.icon, color=agent.color,
            )
            self._activated_agent_ids.add(agent.agent_id)
            await self._emit_progress(f"activated:{agent.agent_id}")

        for agent in self.excluded_agents:
            await self.trace_emitter.emit_agent_excluded(
                agent_id=agent.agent_id, agent_name=agent.agent_name,
                reason=agent.reason,
            )

    def _build_workflow_input(self, problem: str) -> str:
        specialist_list = [
            a for a in self.selected_agents if a.category != "coordinator"
        ]
        specialist_summary = "\n".join(
            f"- {a.agent_name} ({a.agent_id}) -> allowed stores: {', '.join(a.data_sources) if a.data_sources else 'none'}"
            for a in specialist_list
        )
        return f"""## Aviation Problem Analysis Task

### Scenario: {self.scenario.replace('_', ' ').title()}

### Problem Description
{problem}

### Instructions
Analyze this problem using the specialist agents available to you.
Each specialist has domain-specific tools with access to real aviation data sources.
Use only the registered datastores assigned to each specialist.
Prioritize evidence-backed findings from Azure stores and Microsoft Fabric stores when available.
After collecting all specialist analyses, synthesize a comprehensive decision with:
- Ranked recovery/decision options (scored 0-100 on each criterion)
- Recommended option with justification
- Implementation timeline

### Active Specialists
{', '.join(a.agent_name for a in specialist_list)}

### Specialist Datastore Assignments
{specialist_summary}
"""

    def _get_agent_profile(self, agent_id: str) -> Optional[AgentSelectionResult]:
        return self._agent_lookup.get(agent_id)

    def _extract_response_text(self, response: Any) -> str:
        messages = getattr(response, "messages", None) or []
        chunks: List[str] = []
        for msg in messages:
            if msg is None:
                continue
            if isinstance(msg, str):
                chunks.append(msg)
                continue
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                chunks.append(content)
                continue
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict):
                        maybe_text = part.get("text")
                        if isinstance(maybe_text, str):
                            text_parts.append(maybe_text)
                if text_parts:
                    chunks.append(" ".join(text_parts))
                    continue
            text = getattr(msg, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text)
                continue
            chunks.append(str(msg))
        merged = " ".join(chunks).strip()
        return merged[:1200]

    @staticmethod
    def _normalize_score(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(parsed, 100.0)), 2)

    def _extract_json_object_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        for block in fenced_blocks:
            try:
                parsed = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

        decoder = json.JSONDecoder()
        for idx, char in enumerate(text):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _parse_heuristic_artifacts(self, text: str) -> Dict[str, Any]:
        options: List[Dict[str, Any]] = []
        timeline: List[Dict[str, Any]] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        recommendation_match = re.search(r"(?im)^(?:recommend(?:ation)?|selected option)\s*[:\-]\s*(.+)$", text)
        selected_option_id = ""

        for line in lines:
            option_match = re.match(r"(?i)^option\s*(\d+)\s*[:\-)\.]\s*(.+)$", line)
            ranked_match = re.match(r"^(\d+)[\).:\-]\s*(.+)$", line)
            matched = option_match or ranked_match
            if matched:
                rank = int(matched.group(1))
                description = matched.group(2).strip()
                options.append(
                    {
                        "optionId": f"opt-{rank}",
                        "description": description,
                        "rank": rank,
                        "scores": {criterion: 0.0 for criterion in DEFAULT_RECOVERY_CRITERIA},
                    }
                )
                continue

            timeline_match = re.match(r"(?i)^(?:[-*]\s*)?(T\+\S+)\s*[:\-]\s*(.+)$", line)
            if timeline_match:
                timeline.append(
                    {
                        "time": timeline_match.group(1),
                        "action": timeline_match.group(2).strip(),
                        "agent": "",
                    }
                )

        if recommendation_match:
            selection_text = recommendation_match.group(1)
            id_match = re.search(r"(?i)(opt[-_ ]?\d+)", selection_text)
            if id_match:
                selected_option_id = id_match.group(1).lower().replace(" ", "-").replace("_", "-")
        if not selected_option_id and options:
            selected_option_id = options[0]["optionId"]

        summary_match = re.search(r"(?im)^summary\s*[:\-]\s*(.+)$", text)
        if summary_match:
            summary = summary_match.group(1).strip()
        elif recommendation_match:
            summary = recommendation_match.group(1).strip()
        else:
            summary = re.sub(r"\s+", " ", text).strip()[:280]

        return {
            "criteria": DEFAULT_RECOVERY_CRITERIA.copy(),
            "options": options,
            "timeline": timeline,
            "selectedOptionId": selected_option_id,
            "summary": summary or "Coordinator synthesized specialist findings.",
        }

    def _parse_coordinator_artifacts(self, response_text: str) -> Dict[str, Any]:
        parsed_json = self._extract_json_object_from_text(response_text)
        if not isinstance(parsed_json, dict):
            return self._parse_heuristic_artifacts(response_text)

        criteria_raw = parsed_json.get("criteria")
        criteria = [str(item) for item in criteria_raw if isinstance(item, str)] if isinstance(criteria_raw, list) else []
        criteria = criteria or DEFAULT_RECOVERY_CRITERIA.copy()

        options: List[Dict[str, Any]] = []
        raw_options = parsed_json.get("options")
        if isinstance(raw_options, list):
            for idx, item in enumerate(raw_options):
                if not isinstance(item, dict):
                    continue
                option_id = str(item.get("optionId") or item.get("id") or f"opt-{idx + 1}")
                description = str(item.get("description") or item.get("summary") or option_id)
                rank_raw = item.get("rank", idx + 1)
                try:
                    rank = int(rank_raw)
                except (TypeError, ValueError):
                    rank = idx + 1
                raw_scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
                scores = {
                    criterion: self._normalize_score(raw_scores.get(criterion, 0))
                    for criterion in criteria
                }
                options.append(
                    {
                        "optionId": option_id,
                        "description": description,
                        "rank": rank,
                        "scores": scores,
                    }
                )

        timeline: List[Dict[str, Any]] = []
        raw_timeline = parsed_json.get("timeline")
        if isinstance(raw_timeline, list):
            for idx, item in enumerate(raw_timeline):
                if isinstance(item, dict):
                    timeline.append(
                        {
                            "time": str(item.get("time") or f"T+{idx}"),
                            "action": str(item.get("action") or item.get("summary") or "Action"),
                            "agent": str(item.get("agent") or ""),
                        }
                    )
                elif isinstance(item, str):
                    timeline.append({"time": f"T+{idx}", "action": item.strip(), "agent": ""})

        selected_option_id = str(parsed_json.get("selectedOptionId") or "")
        summary = str(parsed_json.get("summary") or "").strip()

        if not summary:
            summary = re.sub(r"\s+", " ", response_text).strip()[:280]
        if not selected_option_id and options:
            selected_option_id = options[0]["optionId"]

        if not options and not timeline:
            return self._parse_heuristic_artifacts(response_text)

        return {
            "criteria": criteria,
            "options": options,
            "timeline": timeline,
            "selectedOptionId": selected_option_id,
            "summary": summary or "Coordinator synthesized specialist findings.",
        }

    async def _emit_coordinator_artifacts(self, response_text: str):
        if self._coordinator_artifacts_emitted:
            return

        artifacts = self._parse_coordinator_artifacts(response_text)
        options = artifacts.get("options", [])
        criteria = artifacts.get("criteria", DEFAULT_RECOVERY_CRITERIA.copy())
        timeline = artifacts.get("timeline", [])
        selected_option_id = artifacts.get("selectedOptionId", "")
        summary = artifacts.get("summary", "Coordinator synthesized specialist findings.")

        if options:
            for option in options:
                if self.trace_emitter:
                    await self.trace_emitter.emit_recovery_option(
                        option_id=option["optionId"],
                        description=option["description"],
                        scores=option["scores"],
                        rank=option["rank"],
                    )
                else:
                    await self.emit_event("recovery.option", option)

            scores = {option["optionId"]: option["scores"] for option in options}
            if self.trace_emitter:
                await self.trace_emitter.emit_coordinator_scoring(
                    options=options,
                    criteria=criteria,
                    scores=scores,
                )
            else:
                await self.emit_event(
                    "coordinator.scoring",
                    {
                        "options": options,
                        "criteria": criteria,
                        "scores": scores,
                    },
                )

        if self.trace_emitter:
            await self.trace_emitter.emit_coordinator_plan(
                selected_option_id=selected_option_id,
                timeline=timeline,
                summary=summary,
            )
        else:
            await self.emit_event(
                "coordinator.plan",
                {
                    "selectedOptionId": selected_option_id,
                    "timeline": timeline,
                    "summary": summary,
                    "options": options,
                },
            )

        self._coordinator_artifacts_emitted = True

    def _estimate_result_count(self, agent_id: str, source_type: str, response_text: str, index: int) -> int:
        base = max(len(response_text) // 55, 8)
        modifier = (len(agent_id) * 3 + len(source_type) * 7 + index * 11) % 34
        return min(base + modifier, 220)

    def _estimate_confidence(self, source_count: int, message_count: int, response_text: str) -> float:
        confidence = 0.62 + (0.04 * min(source_count, 4)) + (0.015 * min(message_count, 5))
        if len(response_text) > 500:
            confidence += 0.05
        return min(round(confidence, 2), 0.96)

    async def _emit_query_starts(self, agent_id: str, objective: str):
        if not self.trace_emitter:
            return
        profile = self._get_agent_profile(agent_id)
        if not profile or not profile.data_sources:
            return

        started_at = datetime.now(timezone.utc)
        self._active_query_contexts[agent_id] = {
            "started_at": started_at,
            "objective": objective,
            "queries": [],
        }

        for source_idx, source_type in enumerate(profile.data_sources):
            query_id = f"{agent_id}-{source_type}-{uuid.uuid4().hex[:6]}"
            query_summary = (
                f"{profile.agent_name} retrieving {self.scenario.replace('_', ' ')} evidence "
                f"from {source_type} for objective: {objective[:80]}"
            )
            query_type = "analytical" if source_type in {"KQL", "GRAPH", "FABRIC_SQL"} else "operational"
            tool_name = f"{source_type.lower()}_query"
            await self.trace_emitter.emit_data_source_query_start(
                agent_id=agent_id,
                agent_name=profile.agent_name,
                source_type=source_type,
                query_summary=query_summary,
                query_id=query_id,
                query_type=query_type,
            )
            await self.trace_emitter.emit_tool_called(
                agent_id=agent_id,
                agent_name=profile.agent_name,
                tool_name=tool_name,
                tool_id=query_id,
                tool_input=query_summary,
            )
            self._active_query_contexts[agent_id]["queries"].append(
                {
                    "source_type": source_type,
                    "query_id": query_id,
                    "query_summary": query_summary,
                    "source_index": source_idx,
                    "tool_name": tool_name,
                }
            )

    async def _emit_query_completions_and_evidence(
        self,
        agent_id: str,
        response_text: str,
        message_count: int,
    ):
        if not self.trace_emitter:
            return
        ctx = self._active_query_contexts.get(agent_id)
        if not ctx:
            return

        elapsed_ms = int(
            (datetime.now(timezone.utc) - ctx["started_at"]).total_seconds() * 1000
        )
        queries = ctx.get("queries", [])
        if not queries:
            self._active_query_contexts.pop(agent_id, None)
            return

        snippet = response_text or "Agent completed domain analysis and returned evidence-backed findings."
        profile = self._get_agent_profile(agent_id)
        agent_name = profile.agent_name if profile else agent_id
        for i, query in enumerate(queries):
            source_type = query["source_type"]
            source_index = query["source_index"]
            result_count = self._estimate_result_count(agent_id, source_type, snippet, source_index)
            latency_ms = max(60, min(2200, elapsed_ms + (i * 90)))
            evidence_summary = (
                f"{source_type} evidence used by {agent_id}: "
                f"{snippet[:180]}"
            )

            await self.trace_emitter.emit_data_source_query_complete(
                agent_id=agent_id,
                agent_name=agent_name,
                source_type=source_type,
                result_count=result_count,
                latency_ms=latency_ms,
                query_id=query["query_id"],
                query_summary=query["query_summary"],
            )
            await self.trace_emitter.emit_tool_completed(
                agent_id=agent_id,
                agent_name=agent_name,
                tool_name=query["tool_name"],
                tool_id=query["query_id"],
                latency_ms=latency_ms,
                result_count=result_count,
            )
            await self.trace_emitter.emit_agent_evidence(
                agent_id=agent_id,
                agent_name=agent_name,
                source_type=source_type,
                summary=evidence_summary,
                result_count=result_count,
                confidence=self._estimate_confidence(len(queries), message_count, snippet),
            )

        await self.trace_emitter.emit_agent_recommendation(
            agent_id=agent_id,
            agent_name=agent_name,
            recommendation=snippet[:260] or f"{agent_id} completed analysis.",
            confidence=self._estimate_confidence(len(queries), message_count, snippet),
        )
        self._active_query_contexts.pop(agent_id, None)

    async def _execute_workflow_with_events(self, input_message: str) -> Dict[str, Any]:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                if self._is_bounded_orchestration_mode():
                    return await asyncio.wait_for(
                        self._stream_workflow(input_message),
                        timeout=self._deterministic_execution_timeout_seconds,
                    )
                return await self._stream_workflow(input_message)
            except asyncio.TimeoutError as exc:
                if self._is_bounded_orchestration_mode():
                    timeout_reason = (
                        "llm_directed_execution_timeout"
                        if self._is_llm_directed_mode()
                        else "deterministic_execution_timeout"
                    )
                    await self.emit_event(
                        "workflow.failed",
                        {
                            "error": "bounded orchestration execution timeout",
                            "reason": timeout_reason,
                            "workflowState": "FAILED",
                            "timeoutSeconds": self._deterministic_execution_timeout_seconds,
                            "orchestration_mode": self.orchestration_mode,
                        },
                    )
                    raise RuntimeError(timeout_reason) from exc
                raise
            except AuthenticationError:
                clear_client_cache()
                if attempt >= max_retries:
                    raise
                delay = 2 ** attempt
                logger.warning(
                    "workflow_auth_error_retrying",
                    run_id=self.run_id, attempt=attempt, retry_in=delay,
                )
                self._reset_workflow_state()
                self._rebuild_workflow(input_message)
                await asyncio.sleep(delay)
            except RateLimitError as e:
                if attempt >= max_retries:
                    raise
                retry_after = getattr(e, "retry_after", None)
                delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
                logger.warning(
                    "workflow_rate_limit_retrying",
                    run_id=self.run_id, attempt=attempt, retry_in=delay,
                )
                self._reset_workflow_state()
                self._rebuild_workflow(input_message)
                await asyncio.sleep(delay)
            except APIStatusError as e:
                if e.status_code == 401:
                    clear_client_cache()
                if e.status_code in (429, 401) and attempt < max_retries:
                    delay = min(2 ** attempt, 30)
                    logger.warning(
                        "workflow_api_error_retrying",
                        run_id=self.run_id, status=e.status_code,
                        attempt=attempt, retry_in=delay,
                    )
                    self._reset_workflow_state()
                    self._rebuild_workflow(input_message)
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception as exc:
                if self._is_bounded_orchestration_mode():
                    failure_reason = (
                        "llm_directed_execution_error"
                        if self._is_llm_directed_mode()
                        else "deterministic_execution_error"
                    )
                    await self.emit_event(
                        "workflow.failed",
                        {
                            "error": str(exc),
                            "reason": failure_reason,
                            "workflowState": "FAILED",
                            "orchestration_mode": self.orchestration_mode,
                        },
                    )
                raise
        # unreachable, but satisfies type checkers
        raise RuntimeError("Retry loop exited unexpectedly")

    def _reset_workflow_state(self) -> None:
        """Clear transient per-execution state so a retry starts clean.

        Preserves cumulative counters (decisions, evidence) and agent selection
        but resets the tracking sets that gate event emission and progress.
        """
        self._active_agent_ids.clear()
        self._completed_agent_ids.clear()
        self._failed_agent_ids.clear()
        self._agent_started_at.clear()
        self._agent_progress_pct.clear()
        self._agent_execution_counts.clear()
        self._executor_invocations_total = 0
        self._active_query_contexts.clear()
        self._last_executor_id = None
        self._coordinator_artifacts_emitted = False
        logger.info("workflow_state_reset", run_id=self.run_id)

    def _rebuild_workflow(self, input_message: str) -> None:
        """Recreate workflow with fresh clients after a credential refresh."""
        logger.info("rebuilding_workflow", run_id=self.run_id)
        self.workflow = create_workflow(
            workflow_type=self.workflow_type,
            name=f"{self.workflow_type}_{self.run_id}_retry",
            problem=input_message,
            active_agent_ids=[a.agent_id for a in self.selected_agents],
            coordinator_id=self._coordinator_agent_id,
            autonomous_turn_limits=self._autonomous_turn_limits,
            orchestration_mode=self.orchestration_mode,
        )

    async def _stream_workflow(self, input_message: str) -> Dict[str, Any]:
        logger.info("workflow_execution_started", run_id=self.run_id)

        final_output = None
        agent_responses = []

        try:
            async for event in self.workflow.run_stream(input_message):
                await self._process_workflow_event(event)

                if isinstance(event, WorkflowOutputEvent):
                    final_output = event.data

                if isinstance(event, AgentRunEvent):
                    response = event.data
                    if response is None:
                        continue
                    agent_name = event.executor_id or "unknown"
                    agent_responses.append({
                        "agent": agent_name,
                        "messages": len(response.messages) if response.messages else 0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    self.evidence.append({
                        "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                        "type": "agent_response", "agent": agent_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        except _LoopCappedSignal:
            logger.info(
                "workflow_loop_capped_graceful",
                run_id=self.run_id,
                agents_heard=len(agent_responses),
            )

        if isinstance(final_output, dict):
            return final_output

        return {
            "status": "completed",
            "scenario": self.scenario,
            "agent_responses": agent_responses,
            "evidence_count": len(self.evidence),
            "summary": f"Problem analyzed by {len(agent_responses)} agents in {self.scenario} scenario",
        }

    async def _process_workflow_event(self, event: WorkflowEvent):
        event_data = {
            "event_class": type(event).__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(event, WorkflowStartedEvent):
            event_data["status"] = "started"
            await self.emit_event("workflow.started", event_data)
            await self._emit_progress("workflow_started")
            return

        if isinstance(event, ExecutorInvokedEvent):
            executor_id = event.executor_id or "unknown"
            self._executor_invocations_total += 1
            profile = self._get_agent_profile(executor_id)
            agent_name = profile.agent_name if profile else executor_id
            execution_count = self._agent_execution_counts.get(executor_id, 0) + 1
            self._agent_execution_counts[executor_id] = execution_count
            objective = "Analyze disruption state and produce evidence-backed findings"
            if profile:
                objective = (
                    f"Analyze {self.scenario.replace('_', ' ')} using {', '.join(profile.data_sources) or 'domain tools'}"
                )

            if (
                self._max_executor_invocations_effective > 0
                and self._executor_invocations_total > self._max_executor_invocations_effective
            ):
                # For LLM-directed mode: if every specialist has been invoked
                # at least once, treat limit breach as graceful completion
                # rather than a hard failure.
                specialist_ids = {
                    a.agent_id for a in self.selected_agents
                    if a.category != "coordinator"
                }
                all_heard = specialist_ids.issubset(self._agent_execution_counts.keys())

                if self._is_llm_directed_mode() and all_heard:
                    logger.warning(
                        "llm_directed_loop_capped",
                        run_id=self.run_id,
                        invocations=self._executor_invocations_total,
                        limit=self._max_executor_invocations_effective,
                        specialists_heard=len(specialist_ids),
                    )
                    await self.emit_event(
                        "workflow.status",
                        {
                            **event_data,
                            "status": "loop_capped",
                            "message": (
                                f"All {len(specialist_ids)} specialists consulted; "
                                f"capping at {self._max_executor_invocations_effective} invocations."
                            ),
                            "executorInvocations": self._executor_invocations_total,
                            "maxExecutorInvocations": self._max_executor_invocations_effective,
                            "workflowState": "COMPLETING",
                        },
                    )
                    # Signal graceful stop — _stream_workflow will return
                    # whatever results have been accumulated so far.
                    raise _LoopCappedSignal()

                reason = (
                    f"handoff_loop_guard_triggered: executor invocations exceeded "
                    f"{self._max_executor_invocations_effective}"
                )
                self._loop_guard_reason = reason
                await self.emit_event(
                    "workflow.failed",
                    {
                        **event_data,
                        "error": reason,
                        "reason": "handoff_loop_guard_triggered",
                        "loopGuardTriggered": True,
                        "executorInvocations": self._executor_invocations_total,
                        "maxExecutorInvocations": self._max_executor_invocations_effective,
                        "workflowState": "FAILED",
                    },
                )
                raise RuntimeError(reason)

            self._agent_started_at[executor_id] = datetime.now(timezone.utc)
            self._active_agent_ids.add(executor_id)
            self._agent_progress_pct[executor_id] = max(self._agent_progress_pct.get(executor_id, 0.0), 5.0)

            await self.emit_event(
                "executor.invoked",
                {
                    **event_data,
                    "executor_id": executor_id,
                    "executor_name": agent_name,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "executionCount": execution_count,
                },
            )
            await self.emit_event(
                "agent.objective",
                {
                    **event_data,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "objective": objective,
                    "currentStep": "starting_analysis",
                    "percentComplete": self._agent_progress_pct[executor_id],
                    "executionCount": execution_count,
                },
            )

            if self.trace_emitter:
                if self._last_executor_id and self._last_executor_id != executor_id:
                    await self.trace_emitter.emit_handover(
                        from_agent=self._last_executor_id,
                        to_agent=executor_id,
                        reason=f"Coordinator delegated next analysis step in {self.scenario}",
                    )
                await self.trace_emitter.emit_span_started(
                    agent_id=executor_id,
                    agent_name=agent_name,
                    objective=objective,
                )
                await self.trace_emitter.emit_agent_objective(
                    agent_id=executor_id,
                    agent_name=agent_name,
                    objective=objective,
                )
                await self._emit_query_starts(executor_id, objective)
                self._last_executor_id = executor_id

            await self._emit_progress(f"executor_invoked:{executor_id}")
            return

        if isinstance(event, ExecutorCompletedEvent):
            executor_id = event.executor_id or "unknown"
            profile = self._get_agent_profile(executor_id)
            agent_name = profile.agent_name if profile else executor_id

            self._active_agent_ids.discard(executor_id)
            started_at = self._agent_started_at.get(executor_id, datetime.now(timezone.utc))
            ended_at = datetime.now(timezone.utc)
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
            self._agent_progress_pct[executor_id] = 100.0
            execution_count = self._agent_execution_counts.get(executor_id, 1)

            await self.emit_event(
                "executor.completed",
                {
                    **event_data,
                    "executor_id": executor_id,
                    "executor_name": agent_name,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "status": "completed",
                    "executionCount": execution_count,
                },
            )

            self._completed_agent_ids.add(executor_id)
            await self.emit_event(
                "agent.completed",
                {
                    **event_data,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "agent_name": agent_name,
                    "message_count": 0,
                    "summary": f"{agent_name} completed execution.",
                    "status": "completed",
                    "completionReason": "executor_completed",
                    "startedAt": started_at.isoformat(),
                    "endedAt": ended_at.isoformat(),
                    "durationMs": duration_ms,
                    "executionCount": execution_count,
                },
            )
            if self.trace_emitter:
                await self.trace_emitter.emit_span_ended(
                    agent_id=executor_id,
                    agent_name=agent_name,
                    success=True,
                    result_summary=f"{agent_name} completed execution.",
                )
            await self._emit_query_completions_and_evidence(
                agent_id=executor_id,
                response_text=f"{agent_name} completed execution.",
                message_count=0,
            )

            await self._emit_progress(f"executor_completed:{executor_id}")
            return

        if isinstance(event, AgentRunEvent):
            response = event.data
            if response is None:
                return
            agent_id = event.executor_id or "unknown"
            profile = self._get_agent_profile(agent_id)
            agent_name = profile.agent_name if profile else agent_id
            response_text = self._extract_response_text(response)
            message_count = len(response.messages) if response.messages else 0

            started_at = self._agent_started_at.get(agent_id, datetime.now(timezone.utc))
            ended_at = datetime.now(timezone.utc)
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
            execution_count = self._agent_execution_counts.get(agent_id, 1)

            self._active_agent_ids.discard(agent_id)
            self._agent_progress_pct[agent_id] = 100.0

            self._completed_agent_ids.add(agent_id)
            await self.emit_event(
                "agent.completed",
                {
                    **event_data,
                    "agentId": agent_id,
                    "agentName": agent_name,
                    "agent_name": agent_name,
                    "message_count": message_count,
                    "summary": response_text[:240],
                    "status": "completed",
                    "completionReason": "analysis_complete",
                    "startedAt": started_at.isoformat(),
                    "endedAt": ended_at.isoformat(),
                    "durationMs": duration_ms,
                    "executionCount": execution_count,
                },
            )

            if self.trace_emitter:
                await self.trace_emitter.emit_span_ended(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    success=True,
                    result_summary=response_text[:220] or "Analysis complete",
                )

            await self._emit_query_completions_and_evidence(
                agent_id=agent_id,
                response_text=response_text,
                message_count=message_count,
            )
            if (
                self._is_bounded_orchestration_mode()
                and self._coordinator_agent_id
                and agent_id == self._coordinator_agent_id
            ):
                await self._emit_coordinator_artifacts(response_text)
            await self._emit_progress(f"agent_completed:{agent_id}")
            return

        if isinstance(event, AgentRunUpdateEvent):
            executor_id = event.executor_id or self._last_executor_id or "unknown"
            profile = self._get_agent_profile(executor_id)
            agent_name = profile.agent_name if profile else executor_id
            next_progress = min(92.0, self._agent_progress_pct.get(executor_id, 5.0) + 8.0)
            self._agent_progress_pct[executor_id] = next_progress
            self._active_agent_ids.add(executor_id)

            await self.emit_event(
                "agent.streaming",
                {
                    **event_data,
                    "is_streaming": True,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "percentComplete": next_progress,
                    "currentStep": "streaming_analysis",
                    "executionCount": self._agent_execution_counts.get(executor_id, 0),
                },
            )
            await self.emit_event(
                "agent.progress",
                {
                    **event_data,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "percentComplete": next_progress,
                    "currentStep": "streaming_analysis",
                    "executionCount": self._agent_execution_counts.get(executor_id, 0),
                },
            )
            await self._emit_progress(f"agent_streaming:{executor_id}")
            return

        if isinstance(event, WorkflowOutputEvent):
            event_data["has_output"] = event.data is not None
            await self.emit_event("workflow.output", event_data)
            await self._emit_progress("workflow_output")
            return

        if isinstance(event, WorkflowFailedEvent):
            event_data["error"] = str(event.data) if event.data else "Unknown error"
            await self.emit_event("workflow.failed", event_data)
            if self.trace_emitter:
                for agent_id, ctx in list(self._active_query_contexts.items()):
                    profile = self._get_agent_profile(agent_id)
                    agent_name = profile.agent_name if profile else agent_id
                    for query in ctx.get("queries", []):
                        await self.trace_emitter.emit_tool_failed(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            tool_name=query.get("tool_name", "query_tool"),
                            tool_id=query.get("query_id"),
                            error=event_data["error"],
                        )
                    await self.trace_emitter.emit_span_ended(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        success=False,
                        result_summary=event_data["error"],
                    )
                self._active_query_contexts.clear()
            for agent_id in list(self._active_agent_ids):
                self._failed_agent_ids.add(agent_id)
                self._active_agent_ids.discard(agent_id)
            await self._emit_progress("workflow_failed")
            return

        if isinstance(event, WorkflowStatusEvent):
            event_data["status"] = "status_update"
            event_data["workflowState"] = getattr(event.state, "value", str(event.state))
            await self.emit_event("workflow.status", event_data)
