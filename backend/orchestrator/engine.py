"""
Central orchestrator engine for aviation multi-agent problem solving.
Uses Microsoft Agent Framework workflow patterns for orchestration.

Supports:
- Sequential: Linear agent execution (legacy 3-agent)
- Handoff: LLM-driven coordinator delegation to dynamic specialist subsets
"""

import asyncio
import ast
import json
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

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
from agent_framework._workflows._handoff import HandoffSentEvent
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


RUNTIME_FAILURE_REASON_CODES = {
    "coordinator_no_specialist_handoff",
    "coordinator_options_invalid_shape",
    "insufficient_specialist_analysis",
}

SPECIALIST_FINDINGS_REQUIRED_KEYS = {
    "executive_summary",
    "evidence_points",
    "recommended_actions",
    "risks",
    "confidence",
}


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
        self._data_source_trace_mode = os.getenv("DATA_SOURCE_TRACE_MODE", "actual").strip().lower() or "actual"
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
        self._agent_invocation_counts: Dict[str, int] = {}
        self._invocation_should_respond: Dict[str, bool] = {}
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
        self._deterministic_stream_update_limit = int(
            os.getenv("DETERMINISTIC_AGENT_STREAM_UPDATE_LIMIT", "24")
        )
        self._deterministic_stream_timeout_seconds = int(
            os.getenv("DETERMINISTIC_AGENT_STREAM_TIMEOUT_SECONDS", "180")
        )
        self._llm_directed_stream_timeout_seconds = int(
            os.getenv("LLM_DIRECTED_AGENT_STREAM_TIMEOUT_SECONDS", "120")
        )
        self._agent_stream_update_counts: Dict[str, int] = {}
        self._agent_stream_last_update_at: Dict[str, datetime] = {}
        self._agent_stream_guarded_invocation_keys: set[str] = set()
        self._agent_stream_throttle_at: Dict[str, datetime] = {}
        self._stream_throttle_td = timedelta(
            milliseconds=int(os.getenv("STREAM_THROTTLE_MS", "500"))
        )
        self._streaming_text_accum: Dict[str, List[str]] = {}
        self._handoff_specialist_snapshots: Dict[str, str] = {}
        self._latest_coordinator_artifacts: Dict[str, Any] = {}
        self._latest_coordinator_response_text: str = ""
        self._coordinator_control_output_detected: bool = False
        self._problem_statement: str = ""
        self._specialist_findings_map: Dict[str, Dict[str, Any]] = {}
        self._phase_lock_enabled: bool = False
        self._phase_transition_time_ms: Optional[int] = None
        self._synthesis_trigger_reason: str = ""
        self._fallback_mode: str = "none"
        self._final_confidence_level: str = "medium"
        self._final_assumptions: List[str] = []
        self._max_specialist_cycles = int(os.getenv("LLM_DIRECTED_MAX_SPECIALIST_CYCLES", "3"))
        self._synthesis_trigger_seconds = int(os.getenv("LLM_DIRECTED_SYNTHESIS_TRIGGER_SECONDS", "120"))
        self._forced_synthesis_noop_cycles = int(os.getenv("LLM_DIRECTED_FORCED_SYNTHESIS_NOOP_CYCLES", "18"))

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

    @staticmethod
    def _is_internal_executor_id(executor_id: str) -> bool:
        normalized = str(executor_id or "").strip().lower()
        if not normalized:
            return True
        if normalized in {"input-conversation", "specialist_aggregator", "end"}:
            return True
        return "request_info" in normalized

    def _specialist_agent_ids(self) -> set[str]:
        return {
            agent.agent_id
            for agent in self.selected_agents
            if agent.category != "coordinator"
        }

    def _domain_agent_ids(self) -> set[str]:
        ids = {agent.agent_id for agent in self.selected_agents}
        if self._coordinator_agent_id:
            ids.add(self._coordinator_agent_id)
        return ids

    def _is_domain_executor_id(self, executor_id: str) -> bool:
        if self._is_internal_executor_id(executor_id):
            return False
        if self.workflow_type != WorkflowType.HANDOFF:
            return True
        domain_ids = self._domain_agent_ids()
        if not domain_ids:
            return True
        return executor_id in domain_ids

    def _is_specialist_executor_id(self, executor_id: str) -> bool:
        if self._is_internal_executor_id(executor_id):
            return False
        if self.workflow_type != WorkflowType.HANDOFF:
            return executor_id != (self._coordinator_agent_id or "")
        specialist_ids = self._specialist_agent_ids()
        if not specialist_ids:
            return executor_id != (self._coordinator_agent_id or "")
        return executor_id in specialist_ids

    @staticmethod
    def _extract_should_respond_flag(invocation_data: Any) -> Optional[bool]:
        if invocation_data is None:
            return None
        if isinstance(invocation_data, dict):
            value = invocation_data.get("should_respond")
            if isinstance(value, bool):
                return value
            return None
        value = getattr(invocation_data, "should_respond", None)
        if isinstance(value, bool):
            return value
        return None

    def _current_invocation_count(self, executor_id: str) -> int:
        return int(self._agent_invocation_counts.get(executor_id, 0))

    def _invocation_guard_key(self, executor_id: str, invocation_count: Optional[int] = None) -> str:
        resolved_count = invocation_count if invocation_count is not None else self._current_invocation_count(executor_id)
        return f"{executor_id}:{max(int(resolved_count), 0)}"

    def _is_noop_invocation(self, executor_id: str, invocation_count: Optional[int] = None) -> bool:
        guard_key = self._invocation_guard_key(executor_id, invocation_count=invocation_count)
        return self._invocation_should_respond.get(guard_key, True) is False

    def _is_orchestration_noise_text(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
        if not normalized:
            return True
        if normalized.startswith("## aviation problem analysis task"):
            return True
        if "streaming traces now. final answer will appear when the run completes." in normalized:
            return True
        if "specialist agents contributed findings" in normalized and normalized.startswith("analysis complete"):
            return True
        if "handoff_to" in normalized:
            parsed = self._parse_possible_json_payload(text)
            if parsed and self._is_control_handoff_payload(parsed):
                return True
            if normalized.startswith("{") and '"handoff_to"' in normalized and "finalanswer" not in normalized:
                return True
        return False

    def _is_substantive_response_text(self, text: str) -> bool:
        candidate = str(text or "").strip()
        if not candidate:
            return False
        if self._is_orchestration_noise_text(candidate):
            return False
        return len(candidate) >= 20

    def _is_agent_update_event(self, event: WorkflowEvent) -> bool:
        """Compatibility helper for framework versions with renamed update event classes."""
        return isinstance(event, AgentRunUpdateEvent) or type(event).__name__ == "AgentRunUpdateEvent"

    @staticmethod
    def _is_super_step_started_event(event: WorkflowEvent) -> bool:
        return type(event).__name__ == "SuperStepStartedEvent"

    @staticmethod
    def _is_super_step_completed_event(event: WorkflowEvent) -> bool:
        return type(event).__name__ == "SuperStepCompletedEvent"

    def _current_substantive_coordinator_signal(self) -> str:
        candidates = [
            self._latest_coordinator_artifacts.get("finalAnswer"),
            self._latest_coordinator_artifacts.get("summary"),
            self._latest_coordinator_response_text,
        ]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if self._is_substantive_response_text(text):
                return text[:1200]
        return ""

    @staticmethod
    def _normalize_event_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if payload is None:
            return {}
        payload_preview = re.sub(r"\s+", " ", str(payload)).strip()[:300]
        return {
            "message": payload_preview,
            "raw_payload_preview": payload_preview,
            "payload_type": type(payload).__name__,
        }

    async def emit_event(self, event_type: str, payload: Any):
        if self.event_emitter:
            payload_dict = self._normalize_event_payload(payload)
            actor = payload_dict.get("actor")
            if not isinstance(actor, dict):
                agent_id = payload_dict.get("agentId") or payload_dict.get("agent_id") or payload_dict.get("executor_id")
                agent_name = payload_dict.get("agentName") or payload_dict.get("agent_name") or payload_dict.get("executor_name")
                if agent_id:
                    actor = {"kind": "agent", "id": agent_id, "name": agent_name or agent_id}
                else:
                    actor = {"kind": "orchestrator", "id": "orchestrator", "name": "Orchestrator"}
            full_payload = {
                "run_id": self.run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                **payload_dict,
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
            **self._context_quality_metrics(),
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
        self._problem_statement = problem

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

            summary = str(result.get("summary", "") or "") if isinstance(result, dict) else ""
            answer = str(result.get("answer", "") or "") if isinstance(result, dict) else ""
            await self.emit_event("orchestrator.run_completed", {
                "result": result,
                "answer": answer,
                "summary": summary,
                "decision_count": len(self.decisions),
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
        selectable_profiles = [
            profile for profile in all_profiles
            if profile.category != "placeholder" and profile.agent_id in selected_baseline
        ]

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
            "Rules: include exactly one coordinator agent and put coordinator last in executionOrder. "
            "IMPORTANT: Only select agents from the provided candidateAgents list. "
            "These have been pre-filtered for the detected scenario."
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
- Confidence level (high/medium/low), assumptions, and evidence coverage

Specialist output contract:
- Emit a `SPECIALIST_FINDINGS` JSON block with:
  `executive_summary`, `evidence_points[]`, `recommended_actions[]`, `risks[]`, `confidence` (0..1)

### Active Specialists
{', '.join(a.agent_name for a in specialist_list)}

### Specialist Datastore Assignments
{specialist_summary}
"""

    def _get_agent_profile(self, agent_id: str) -> Optional[AgentSelectionResult]:
        return self._agent_lookup.get(agent_id)

    def _extract_text_from_content_item(self, item: Any) -> str:
        if item is None:
            return ""
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            for key in ("text", "message"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for key in ("result", "output"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if value is not None:
                    try:
                        serialized = json.dumps(value, ensure_ascii=True)
                    except Exception:
                        serialized = str(value)
                    if serialized.strip():
                        return serialized.strip()
            return ""

        for key in ("text", "message"):
            value = getattr(item, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("result", "output"):
            value = getattr(item, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value is not None:
                try:
                    serialized = json.dumps(value, ensure_ascii=True)
                except Exception:
                    serialized = str(value)
                if serialized.strip():
                    return serialized.strip()
        return ""

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
                    extracted = self._extract_text_from_content_item(part)
                    if extracted:
                        text_parts.append(extracted)
                if text_parts:
                    chunks.append(" ".join(text_parts))
                    continue

            contents = getattr(msg, "contents", None)
            if isinstance(contents, list):
                text_parts = []
                for part in contents:
                    extracted = self._extract_text_from_content_item(part)
                    if extracted:
                        text_parts.append(extracted)
                if text_parts:
                    chunks.append(" ".join(text_parts))
                    continue

            text = getattr(msg, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text)
                continue
            msg_repr = str(msg).strip()
            if msg_repr and "object at 0x" not in msg_repr:
                chunks.append(msg_repr)
        merged = " ".join(chunks).strip()
        # Fallback: try .text property directly (e.g., AgentResponse.text)
        if not merged:
            direct_text = getattr(response, "text", None)
            if isinstance(direct_text, str) and direct_text.strip():
                merged = direct_text.strip()
        return merged[:8000]

    def _extract_text_and_message_count_from_executor_data(self, data: Any) -> Tuple[str, int]:
        if data is None:
            return "", 0

        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if candidate is None:
                continue

            agent_response = getattr(candidate, "agent_response", None)
            if agent_response is not None:
                response_text = self._extract_response_text(agent_response)
                if not response_text:
                    response_text = str(getattr(agent_response, "text", "") or "").strip()
                messages = getattr(agent_response, "messages", None)
                message_count = len(messages) if isinstance(messages, list) else (1 if response_text else 0)
                if response_text:
                    return response_text[:8000], message_count

            full_conversation = getattr(candidate, "full_conversation", None)
            if isinstance(full_conversation, list) and full_conversation:
                response_text = self._extract_response_text(SimpleNamespace(messages=full_conversation))
                if response_text:
                    return response_text[:8000], len(full_conversation)

            if hasattr(candidate, "messages"):
                response_text = self._extract_response_text(candidate)
                messages = getattr(candidate, "messages", None)
                message_count = len(messages) if isinstance(messages, list) else (1 if response_text else 0)
                if response_text:
                    return response_text[:8000], message_count

            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()[:8000], 1

        return "", 0

    @staticmethod
    def _coerce_string_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            items: List[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        items.append(text)
                elif isinstance(item, dict):
                    text = str(
                        item.get("text")
                        or item.get("summary")
                        or item.get("description")
                        or ""
                    ).strip()
                    if text:
                        items.append(text)
                else:
                    text = str(item).strip()
                    if text:
                        items.append(text)
            return items
        if isinstance(value, str):
            lines = []
            for raw_line in value.splitlines():
                cleaned = re.sub(r"^\s*[-*•\d\.\)]\s*", "", raw_line).strip()
                if cleaned:
                    lines.append(cleaned)
            if lines:
                return lines
            compact = value.strip()
            return [compact] if compact else []
        compact = str(value).strip()
        return [compact] if compact else []

    def _normalize_specialist_findings_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None

        if "specialist_findings" in payload and isinstance(payload.get("specialist_findings"), dict):
            payload = payload["specialist_findings"]
        elif "findings" in payload and isinstance(payload.get("findings"), dict):
            payload = payload["findings"]

        executive_summary = str(
            payload.get("executive_summary")
            or payload.get("executiveSummary")
            or payload.get("summary")
            or ""
        ).strip()
        evidence_points = self._coerce_string_list(
            payload.get("evidence_points")
            or payload.get("evidencePoints")
            or payload.get("evidence")
        )
        recommended_actions = self._coerce_string_list(
            payload.get("recommended_actions")
            or payload.get("recommendedActions")
            or payload.get("actions")
            or payload.get("recommendations")
        )
        risks = self._coerce_string_list(payload.get("risks") or payload.get("risk_items"))
        confidence_raw = payload.get("confidence")
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < 0.0 or confidence > 1.0:
            return None

        normalized = {
            "executive_summary": executive_summary,
            "evidence_points": evidence_points,
            "recommended_actions": recommended_actions,
            "risks": risks,
            "confidence": round(confidence, 3),
        }
        if set(normalized.keys()) != SPECIALIST_FINDINGS_REQUIRED_KEYS:
            return None
        if not executive_summary:
            return None
        if not recommended_actions:
            return None
        return normalized

    def _extract_specialist_findings_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        candidate = str(text or "").strip()
        if not candidate:
            return None

        parsed = self._extract_json_object_from_text(candidate)
        if isinstance(parsed, dict):
            normalized = self._normalize_specialist_findings_payload(parsed)
            if normalized:
                return normalized

        heading_aliases = {
            "executive_summary": ("executive summary", "summary"),
            "evidence_points": ("evidence points", "evidence"),
            "recommended_actions": ("recommended actions", "actions", "recommendations"),
            "risks": ("risks", "risk"),
            "confidence": ("confidence",),
        }
        sections: Dict[str, List[str]] = {key: [] for key in heading_aliases.keys()}
        active_key: Optional[str] = None
        for line in candidate.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower().rstrip(":")
            matched_key = None
            for key, aliases in heading_aliases.items():
                if any(lowered == alias or lowered.startswith(f"{alias}:") for alias in aliases):
                    matched_key = key
                    break
            if matched_key:
                active_key = matched_key
                remainder = stripped.split(":", 1)
                if len(remainder) == 2 and remainder[1].strip():
                    sections[active_key].append(remainder[1].strip())
                continue
            if active_key:
                sections[active_key].append(stripped)

        try:
            confidence = float(" ".join(sections["confidence"]).strip()) if sections["confidence"] else -1.0
        except ValueError:
            confidence = -1.0
        parsed_payload = {
            "executive_summary": " ".join(sections["executive_summary"]).strip(),
            "evidence_points": self._coerce_string_list(sections["evidence_points"]),
            "recommended_actions": self._coerce_string_list(sections["recommended_actions"]),
            "risks": self._coerce_string_list(sections["risks"]),
            "confidence": confidence,
        }
        return self._normalize_specialist_findings_payload(parsed_payload)

    def _upsert_specialist_findings(self, agent_id: str, response_text: str) -> bool:
        if not self._is_specialist_executor_id(agent_id):
            return False
        findings = self._extract_specialist_findings_from_text(response_text)
        if not findings:
            return False
        self._specialist_findings_map[agent_id] = findings
        return True

    def _specialist_contribution_count(self) -> int:
        return len(self._specialist_findings_map)

    def _required_specialist_count(self) -> int:
        return len(self._specialist_agent_ids())

    def _context_quality_metrics(self) -> Dict[str, Any]:
        required = self._required_specialist_count()
        contributed = self._specialist_contribution_count()
        real_invocations = max(self._executor_invocations_total, 0)
        noop_invocations = max(sum(
            1 for is_real in self._invocation_should_respond.values() if not is_real
        ), 0)
        ratio = round(noop_invocations / max(real_invocations, 1), 3)
        return {
            "specialist_contribution_count": contributed,
            "specialist_required_count": required,
            "noop_to_real_ratio": ratio,
            "phase_transition_time_ms": self._phase_transition_time_ms,
            "fallback_mode": self._fallback_mode,
            "confidence_level": self._final_confidence_level,
        }

    def _build_specialist_findings_packet(self) -> str:
        if not self._specialist_findings_map:
            return "No structured specialist findings available."
        blocks: List[str] = []
        for agent_id, findings in self._specialist_findings_map.items():
            evidence = "; ".join(findings.get("evidence_points", [])[:3]) or "No quantified evidence provided."
            actions = "; ".join(findings.get("recommended_actions", [])[:3]) or "No actions provided."
            risks = "; ".join(findings.get("risks", [])[:3]) or "No explicit risks provided."
            blocks.append(
                (
                    f"- {agent_id}\n"
                    f"  executive_summary: {findings.get('executive_summary', '')}\n"
                    f"  evidence_points: {evidence}\n"
                    f"  recommended_actions: {actions}\n"
                    f"  risks: {risks}\n"
                    f"  confidence: {findings.get('confidence', 0.0)}"
                )
            )
        return "\n".join(blocks)

    def _derive_confidence_level(self) -> str:
        required = self._required_specialist_count()
        contributed = self._specialist_contribution_count()
        if required <= 0:
            return "low"
        coverage = contributed / max(required, 1)
        if coverage >= 0.8:
            return "high"
        if coverage >= 0.4:
            return "medium"
        return "low"

    def _build_concrete_fallback_result(
        self,
        reason: str,
        agent_responses: Optional[List[Dict[str, Any]]] = None,
        fused_summary: str = "",
    ) -> Dict[str, Any]:
        findings_map = self._specialist_findings_map.copy()
        agent_responses = agent_responses or []
        contributed = len(findings_map)
        required = self._required_specialist_count()
        confidence_level = self._derive_confidence_level()
        self._final_confidence_level = confidence_level
        self._fallback_mode = "sop_concrete"

        assumptions: List[str] = []
        if contributed < required:
            assumptions.append(
                f"Only {contributed} of {required} specialists returned structured findings; missing areas were filled with SOP heuristics."
            )
        if not findings_map:
            assumptions.append("No structured specialist findings were available; recommendations are scenario/SOP-based.")
        if self._problem_statement:
            assumptions.append("Plan is anchored to provided scenario facts and not live operational systems.")
        self._final_assumptions = assumptions

        scenario_default_actions = {
            "hub_disruption": "Execute wave-based hub recovery: prioritize critical banks, legal crew pairings, and passenger reaccommodation at the disrupted hub.",
            "predictive_maintenance": "Escalate targeted inspections for repeat MEL-7200 tails, tighten dispatch gates, and pre-position spare capacity before next departures.",
            "diversion": "Initiate immediate diversion to the nearest suitable alternate with weather and fuel margin, then protect onward connections.",
            "crew_fatigue": "Replace or re-sequence high-duty crews before limit breach, then rebalance rotations using reserve coverage.",
        }
        recommended_action = scenario_default_actions.get(
            self.scenario,
            "Stabilize operations and execute the least-risk recovery wave first.",
        )
        found_recommended_action = False
        evidence_points: List[str] = []
        risks: List[str] = []
        for findings in findings_map.values():
            if not found_recommended_action:
                recommended_actions = findings.get("recommended_actions", [])
                if isinstance(recommended_actions, list):
                    for action in recommended_actions:
                        if isinstance(action, str) and action.strip():
                            recommended_action = action.strip()
                            found_recommended_action = True
                            break
            evidence = findings.get("evidence_points", [])
            if isinstance(evidence, list):
                evidence_points.extend([str(e).strip() for e in evidence if str(e).strip()])
            finding_risks = findings.get("risks", [])
            if isinstance(finding_risks, list):
                risks.extend([str(r).strip() for r in finding_risks if str(r).strip()])

        option_a_desc = recommended_action or "Execute prioritized tail/crew recovery with safety-first constraints."
        option_b_desc = "Delay-bank absorption with targeted passenger protection and controlled curfews."
        option_c_desc = "Conservative hold-and-reassess posture with incremental releases."
        options = [
            {
                "optionId": "opt-1",
                "description": option_a_desc,
                "rank": 1,
                "scores": {
                    "delay_reduction": 78,
                    "crew_margin": 76,
                    "safety_score": 89,
                    "cost_impact": 61,
                    "passenger_impact": 81,
                },
            },
            {
                "optionId": "opt-2",
                "description": option_b_desc,
                "rank": 2,
                "scores": {
                    "delay_reduction": 66,
                    "crew_margin": 72,
                    "safety_score": 87,
                    "cost_impact": 67,
                    "passenger_impact": 73,
                },
            },
            {
                "optionId": "opt-3",
                "description": option_c_desc,
                "rank": 3,
                "scores": {
                    "delay_reduction": 52,
                    "crew_margin": 83,
                    "safety_score": 92,
                    "cost_impact": 70,
                    "passenger_impact": 55,
                },
            },
        ]
        timeline = [
            {"time": "T+0", "action": "Freeze unnecessary dispatch changes and confirm safety constraints.", "agent": "coordinator"},
            {"time": "T+15m", "action": option_a_desc, "agent": "operations_control"},
            {"time": "T+45m", "action": "Revalidate crew legality and re-protect highest-risk passengers.", "agent": "crew_recovery"},
            {"time": "T+90m", "action": "Publish updated recovery bank and monitor knock-on delays.", "agent": "network_impact"},
        ]
        summary = (
            f"Concrete recovery response generated after {reason.replace('_', ' ')}. "
            f"Primary recommendation: {option_a_desc}"
        ).strip()
        if self._is_orchestration_noise_text(summary):
            summary = "Concrete recovery response generated with available specialist evidence and SOP safeguards."
        answer_segments = [summary]
        if evidence_points:
            answer_segments.append(
                "Evidence-backed signals: " + "; ".join(evidence_points[:3]) + "."
            )
        else:
            answer_segments.append("Evidence-backed signals were limited; SOP playbooks were applied.")
        if risks:
            answer_segments.append("Key risks: " + "; ".join(risks[:2]) + ".")
        answer_segments.append(
            "Implement opt-1 immediately, then reassess every 30 minutes against safety and crew legality constraints."
        )
        final_answer = re.sub(r"\s+", " ", " ".join(answer_segments)).strip()[:1600]
        if not self._is_substantive_response_text(final_answer):
            final_answer = "Execute opt-1 immediately with safety-first constraints, then reassess in 30-minute intervals."

        return {
            "status": "completed",
            "scenario": self.scenario,
            "reason": reason,
            "summary": summary,
            "answer": final_answer,
            "criteria": DEFAULT_RECOVERY_CRITERIA.copy(),
            "options": options,
            "timeline": timeline,
            "selectedOptionId": "opt-1",
            "finalAnswer": final_answer,
            "agent_responses": agent_responses,
            "evidence_count": len(self.evidence),
            "isFallback": True,
            "fallbackMode": self._fallback_mode,
            "confidence": confidence_level,
            "assumptions": assumptions,
            "evidenceCoverage": {
                "required": required,
                "contributed": contributed,
            },
            "specialistFindings": findings_map,
            "fusedSummary": fused_summary or self._build_fused_summary(agent_responses),
        }

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

    def _extract_final_answer_from_text(self, text: str) -> str:
        """Extract an explicit user-facing final answer from free-form coordinator text."""
        patterns = [
            r"(?ims)^final\s*answer\s*[:\-]\s*(.+?)(?:\n\s*\n|```|$)",
            r"(?ims)^answer\s*[:\-]\s*(.+?)(?:\n\s*\n|```|$)",
            r"(?ims)^recommendation\s*[:\-]\s*(.+?)(?:\n\s*\n|```|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = re.sub(r"\s+", " ", match.group(1)).strip()
                if candidate:
                    return candidate[:1000]

        without_fenced_json = re.sub(
            r"```(?:json)?\s*.*?```",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()
        if not without_fenced_json:
            return ""

        lines = [line.strip() for line in without_fenced_json.splitlines() if line.strip()]
        if not lines:
            return ""

        generic_prefixes = (
            "coordinator synthesis complete",
            "synthesis complete",
            "analysis complete",
        )
        filtered_lines = [line for line in lines if not line.lower().startswith(generic_prefixes)]
        if not filtered_lines:
            return ""
        chosen_lines = filtered_lines
        candidate = re.sub(r"\s+", " ", " ".join(chosen_lines)).strip()
        return candidate[:1000]

    @staticmethod
    def _is_control_handoff_payload(payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict) or not payload:
            return False
        payload_keys = {str(k).strip() for k in payload.keys()}
        control_keys = {
            "handoff_to",
            "handoffTo",
            "delegate_to",
            "delegateTo",
            "target_agent",
            "targetAgent",
        }
        synthesis_keys = {
            "criteria",
            "options",
            "timeline",
            "selectedOptionId",
            "summary",
            "finalAnswer",
            "answer",
            "recommendation",
        }
        has_control = len(payload_keys & control_keys) > 0
        has_synthesis = len(payload_keys & synthesis_keys) > 0
        return has_control and not has_synthesis

    def _filtered_specialist_responses(self, agent_responses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for response in agent_responses:
            if not isinstance(response, dict):
                continue
            agent_id = str(response.get("agent") or "").strip()
            if not agent_id or not self._is_specialist_executor_id(agent_id):
                continue
            snippet = str(response.get("result_summary") or "").strip()
            if not self._is_substantive_response_text(snippet):
                continue
            filtered.append(response)
        return filtered

    def _has_specialist_participation(self, agent_responses: List[Dict[str, Any]]) -> bool:
        if self._specialist_findings_map:
            return True

        if self._filtered_specialist_responses(agent_responses):
            for response in self._filtered_specialist_responses(agent_responses):
                agent_id = str(response.get("agent") or "").strip()
                snippet = str(response.get("result_summary") or "").strip()
                if agent_id and self._upsert_specialist_findings(agent_id, snippet):
                    return True
        return False

    def _should_fail_coordinator_no_specialist_handoff(
        self,
        artifacts: Dict[str, Any],
        agent_responses: List[Dict[str, Any]],
    ) -> bool:
        if not self._is_bounded_orchestration_mode():
            return False
        specialist_ids = {
            agent.agent_id
            for agent in self.selected_agents
            if agent.category != "coordinator"
        }
        if not specialist_ids:
            return False

        coordinator_id = self._coordinator_agent_id or ""
        coordinator_execution_count = self._agent_execution_counts.get(coordinator_id, 0)
        if coordinator_execution_count <= 0:
            return False

        has_coordinator_output = bool(artifacts) or bool(self._latest_coordinator_response_text.strip())
        if not has_coordinator_output:
            return False

        return not self._has_specialist_participation(agent_responses)

    @staticmethod
    def _choose_selected_option(artifacts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        options = artifacts.get("options")
        if not isinstance(options, list) or not options:
            return None

        selected_option_id = str(artifacts.get("selectedOptionId") or "").strip()
        for option in options:
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("optionId") or "").strip()
            if selected_option_id and option_id == selected_option_id:
                return option

        ranked_options = [opt for opt in options if isinstance(opt, dict)]
        def _rank_value(option: Dict[str, Any]) -> int:
            try:
                return int(option.get("rank", 9999))
            except (TypeError, ValueError):
                return 9999
        ranked_options.sort(key=_rank_value)
        return ranked_options[0] if ranked_options else None

    def _synthesize_answer_from_artifacts(
        self,
        artifacts: Dict[str, Any],
        agent_responses: List[Dict[str, Any]],
    ) -> str:
        """Create a user-facing answer when the coordinator did not return one explicitly."""
        summary = str(artifacts.get("summary") or "").strip()
        if self._is_orchestration_noise_text(summary):
            summary = ""
        selected_option = self._choose_selected_option(artifacts)
        timeline = artifacts.get("timeline") if isinstance(artifacts.get("timeline"), list) else []

        parts: List[str] = []
        if selected_option and isinstance(selected_option, dict):
            description = str(selected_option.get("description") or "").strip()
            if self._is_substantive_response_text(description):
                parts.append(f"Recommended response: {description}.")

        if self._is_substantive_response_text(summary):
            parts.append(summary)

        timeline_actions: List[str] = []
        for item in timeline[:2]:
            if isinstance(item, dict):
                action = str(item.get("action") or "").strip()
                if self._is_substantive_response_text(action):
                    timeline_actions.append(action)
        if timeline_actions:
            parts.append(f"Immediate steps: {'; '.join(timeline_actions)}.")

        if not parts:
            for resp in self._filtered_specialist_responses(agent_responses):
                snippet = str(resp.get("result_summary") or "").strip()
                if self._is_substantive_response_text(snippet):
                    parts.append(snippet)
                if len(parts) >= 2:
                    break

        if not parts:
            fallback = (
                "Structured specialist evidence was limited; applying SOP-based recovery guidance with explicit assumptions."
            )
            return fallback

        joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
        return joined[:1400]

    def _resolve_final_answer(
        self,
        final_output: Any,
        artifacts: Dict[str, Any],
        agent_responses: List[Dict[str, Any]],
        fused_summary: str,
    ) -> str:
        """Resolve the final user-facing answer with deterministic priority."""
        answer = ""
        if isinstance(final_output, dict):
            answer = str(final_output.get("answer") or "").strip()
            if not answer:
                answer = str(final_output.get("finalAnswer") or "").strip()
            if not answer:
                answer = str(final_output.get("recommendation") or "").strip()

        if not answer:
            answer = str(artifacts.get("finalAnswer") or "").strip()
        if not answer:
            answer = self._synthesize_answer_from_artifacts(artifacts, agent_responses)
        if not answer:
            answer = fused_summary
        if self._is_orchestration_noise_text(answer):
            answer = ""
        if not answer:
            answer = "Structured specialist evidence was limited; SOP-based recovery guidance is provided with assumptions."

        return re.sub(r"\s+", " ", answer).strip()[:1600]

    def _build_incomplete_result(self, reason: str) -> Dict[str, Any]:
        return self._build_concrete_fallback_result(reason=reason)

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

        final_answer = self._extract_final_answer_from_text(text)
        if not final_answer:
            final_answer = summary

        return {
            "criteria": DEFAULT_RECOVERY_CRITERIA.copy(),
            "options": options,
            "timeline": timeline,
            "selectedOptionId": selected_option_id,
            "summary": summary or "Coordinator synthesized specialist findings.",
            "finalAnswer": final_answer,
            "confidence": self._derive_confidence_level(),
            "assumptions": list(self._final_assumptions),
            "evidenceCoverage": {
                "required": self._required_specialist_count(),
                "contributed": self._specialist_contribution_count(),
            },
        }

    def _build_fused_summary(self, agent_responses: List[Dict[str, Any]]) -> str:
        """Build a human-readable summary from accumulated agent evidence and responses."""
        parts: List[str] = []
        result_snippets: List[str] = []
        if self._specialist_findings_map:
            for agent_id, findings in self._specialist_findings_map.items():
                parts.append(f"{agent_id} (structured)")
                executive_summary = str(findings.get("executive_summary") or "").strip()
                if executive_summary:
                    result_snippets.append(f"**{agent_id}**: {executive_summary}")
        else:
            filtered_responses = self._filtered_specialist_responses(agent_responses)
            for resp in filtered_responses:
                agent = resp.get("agent", "unknown")
                messages = resp.get("messages", 0)
                parts.append(f"{agent} ({messages} messages)")
                result_text = resp.get("result_summary", "")
                if self._is_substantive_response_text(result_text):
                    result_snippets.append(f"**{agent}**: {result_text}")

        evidence_count = len(self.evidence)
        agent_count = len(self._specialist_findings_map) if self._specialist_findings_map else len(parts)
        required_count = self._required_specialist_count()

        header = (
            f"Analysis complete. {agent_count} specialist agents contributed findings "
            f"(required: {required_count})"
        )
        if parts:
            header += f": {', '.join(parts)}"
        header += f". {evidence_count} evidence items collected."

        if result_snippets:
            return header + "\n\n" + "\n\n".join(result_snippets)
        return header

    def _parse_coordinator_artifacts(self, response_text: str) -> Dict[str, Any]:
        parsed_json = self._extract_json_object_from_text(response_text)
        if not isinstance(parsed_json, dict):
            return self._parse_heuristic_artifacts(response_text)

        if self._is_control_handoff_payload(parsed_json):
            return {
                "criteria": DEFAULT_RECOVERY_CRITERIA.copy(),
                "options": [],
                "timeline": [],
                "selectedOptionId": "",
                "summary": "",
                "finalAnswer": "",
                "confidence": self._derive_confidence_level(),
                "assumptions": list(self._final_assumptions),
                "evidenceCoverage": {
                    "required": self._required_specialist_count(),
                    "contributed": self._specialist_contribution_count(),
                },
                "controlOnly": True,
                "controlPayload": parsed_json,
            }

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
        final_answer = str(
            parsed_json.get("finalAnswer")
            or parsed_json.get("answer")
            or parsed_json.get("recommendation")
            or ""
        ).strip()
        confidence = str(parsed_json.get("confidence") or "").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = self._derive_confidence_level()
        assumptions = self._coerce_string_list(parsed_json.get("assumptions"))
        evidence_coverage_raw = parsed_json.get("evidenceCoverage")
        evidence_coverage = {
            "required": self._required_specialist_count(),
            "contributed": self._specialist_contribution_count(),
        }
        if isinstance(evidence_coverage_raw, dict):
            try:
                evidence_coverage["required"] = int(evidence_coverage_raw.get("required", evidence_coverage["required"]))
                evidence_coverage["contributed"] = int(
                    evidence_coverage_raw.get("contributed", evidence_coverage["contributed"])
                )
            except (TypeError, ValueError):
                pass

        if not summary:
            summary = re.sub(r"\s+", " ", response_text).strip()[:280]
        if not final_answer:
            final_answer = self._extract_final_answer_from_text(response_text)
        if not selected_option_id and options:
            selected_option_id = options[0]["optionId"]

        if not options and not timeline and not summary and not final_answer:
            return self._parse_heuristic_artifacts(response_text)

        return {
            "criteria": criteria,
            "options": options,
            "timeline": timeline,
            "selectedOptionId": selected_option_id,
            "summary": summary or "Coordinator synthesized specialist findings.",
            "finalAnswer": final_answer or summary or "Coordinator synthesized specialist findings.",
            "confidence": confidence,
            "assumptions": assumptions,
            "evidenceCoverage": evidence_coverage,
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
        final_answer = str(artifacts.get("finalAnswer") or "").strip()
        confidence = str(artifacts.get("confidence") or self._derive_confidence_level())
        assumptions = self._coerce_string_list(artifacts.get("assumptions"))
        evidence_coverage = artifacts.get("evidenceCoverage")
        if not isinstance(evidence_coverage, dict):
            evidence_coverage = {
                "required": self._required_specialist_count(),
                "contributed": self._specialist_contribution_count(),
            }

        self._latest_coordinator_artifacts = artifacts
        self._latest_coordinator_response_text = response_text
        self._coordinator_control_output_detected = bool(artifacts.get("controlOnly"))
        if options or timeline or self._is_substantive_response_text(final_answer):
            self._fallback_mode = "none"
            self._final_confidence_level = confidence if confidence in {"high", "medium", "low"} else self._derive_confidence_level()
            self._final_assumptions = assumptions

        if self._coordinator_control_output_detected:
            await self.emit_event(
                "workflow.status",
                {
                    "status": "coordinator_control_output_detected",
                    "workflowState": "RUNNING",
                    "currentStep": "coordinator_control_output_detected",
                    "coordinator_control_output_detected": True,
                    "message": "Coordinator emitted control output without synthesis; awaiting specialist delegation.",
                    **self._context_quality_metrics(),
                },
            )
            return

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
                final_answer=final_answer,
            )
        else:
            await self.emit_event(
                "coordinator.plan",
                {
                    "selectedOptionId": selected_option_id,
                    "timeline": timeline,
                    "summary": summary,
                    "finalAnswer": final_answer,
                    "options": options,
                    "confidence": confidence,
                    "assumptions": assumptions,
                    "evidenceCoverage": evidence_coverage,
                },
            )

        self._coordinator_artifacts_emitted = True

    def _estimate_result_count(self, agent_id: str, source_type: str, response_text: str, index: int) -> int:
        """Estimate result count from response text structure.

        Returns a conservative positive count when the agent produced
        substantive output so the UI displays meaningful data-source
        activity.  Returns 0 only when there is no real response text.
        """
        if not response_text or not response_text.strip():
            return 0
        text = response_text.strip()
        if len(text) < 50:
            return 0
        segments = [
            s for s in re.split(r'\n\n+|\n\s*[-*]\s|\n\s*\d+[.)]\s', text)
            if s.strip()
        ]
        return min(max(1, len(segments)), 25)

    def _estimate_confidence(self, source_count: int, message_count: int, response_text: str) -> float:
        """Return 1.0 if real data sources responded, 0.0 otherwise."""
        return 1.0 if source_count > 0 else 0.0

    def _is_actual_data_source_trace_mode(self) -> bool:
        return self._data_source_trace_mode != "synthetic"

    @staticmethod
    def _parse_possible_json_payload(raw: Any) -> Optional[Dict[str, Any]]:
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        if not text:
            return None

        candidates = [text]
        fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        candidates.extend(block.strip() for block in fenced if block.strip())
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            candidates.append(text[brace_start:brace_end + 1].strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            try:
                parsed = ast.literal_eval(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    @staticmethod
    def _extract_error_code(message: str) -> str:
        if not message:
            return "SOURCE_QUERY_ERROR"
        explicit = re.match(r"^\s*([A-Z0-9_]{3,})\s*:\s*", message)
        if explicit:
            return explicit.group(1)
        lowered = message.lower()
        if "timeout" in lowered or "timed out" in lowered:
            return "SOURCE_TIMEOUT"
        if "not configured" in lowered or "missing" in lowered:
            return "SOURCE_NOT_CONFIGURED"
        if "not installed" in lowered:
            return "SOURCE_DEPENDENCY_MISSING"
        if "token" in lowered or "auth" in lowered or "forbidden" in lowered:
            return "SOURCE_AUTH_ERROR"
        if "schema" in lowered:
            return "SOURCE_SCHEMA_ERROR"
        if "blocked" in lowered:
            return "SOURCE_QUERY_BLOCKED"
        return "SOURCE_QUERY_ERROR"

    @staticmethod
    def _is_explicit_error_citation_title(title: str) -> bool:
        if not title:
            return False
        if re.match(r"^\s*([A-Z0-9_]{3,})\s*:\s*", title):
            return True
        lowered = title.strip().lower()
        if lowered.startswith(
            (
                "sql error:",
                "kql error:",
                "graph error:",
                "search error:",
                "cosmos error:",
                "fabric sql error:",
                "tds error:",
                "error:",
                "unknown search source:",
            )
        ):
            return True
        return lowered in {
            "no database connection",
            "schema insufficient for query",
            "kql schema insufficient",
            "kql endpoint not configured",
            "no fabric token available",
            "no fabric token",
            "no graph endpoint configured",
            "azure-search-documents not installed",
            "search endpoint/key not configured",
            "azure-cosmos not installed",
            "cosmos endpoint not configured",
            "could not generate t-sql",
            "pyodbc not installed",
            "no fabric sql connection string",
        }

    def _infer_result_count_from_payload(self, payload: Dict[str, Any]) -> int:
        for key in ("count", "total", "total_analyzed", "trend_count"):
            value = payload.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        max_len = 0
        for key, value in payload.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in {"citations", "sourceerrors", "errors", "warnings"}:
                continue
            if isinstance(value, list):
                max_len = max(max_len, len(value))
        return max_len

    async def _emit_real_data_source_events_from_tool_payload(
        self,
        agent_id: str,
        payload: Dict[str, Any],
    ) -> None:
        if not self.trace_emitter:
            return
        profile = self._get_agent_profile(agent_id)
        if not profile:
            return
        agent_name = profile.agent_name
        now = datetime.now(timezone.utc)

        citations_raw = payload.get("citations")
        citations: List[Dict[str, Any]] = []
        if isinstance(citations_raw, list):
            for item in citations_raw:
                if isinstance(item, dict):
                    citations.append(item)

        source_errors_raw = payload.get("sourceErrors")
        source_errors: List[Dict[str, Any]] = []
        if isinstance(source_errors_raw, list):
            for item in source_errors_raw:
                if isinstance(item, dict):
                    source_errors.append(item)

        per_source: Dict[str, Dict[str, Any]] = {}
        inferred_count = self._infer_result_count_from_payload(payload)

        for citation in citations:
            source_type = str(
                citation.get("source_type")
                or citation.get("sourceType")
                or citation.get("source")
                or ""
            ).strip()
            if not source_type:
                continue
            title = str(citation.get("title") or "")
            is_error = self._is_explicit_error_citation_title(title)
            entry = per_source.setdefault(
                source_type,
                {"status": "complete", "result_count": inferred_count, "error_code": "", "error_message": "", "query_summary": ""},
            )
            entry["query_summary"] = title[:200] or entry["query_summary"]
            if is_error:
                entry["status"] = "failed"
                entry["result_count"] = 0
                entry["error_code"] = self._extract_error_code(title)
                entry["error_message"] = title[:220]

        for source_err in source_errors:
            source_type = str(source_err.get("sourceType") or source_err.get("source_type") or "").strip()
            if not source_type:
                continue
            message = str(source_err.get("message") or source_err.get("errorMessage") or "Source query failed")
            code = str(source_err.get("errorCode") or self._extract_error_code(message))
            entry = per_source.setdefault(
                source_type,
                {"status": "failed", "result_count": 0, "error_code": code, "error_message": message[:220], "query_summary": ""},
            )
            entry["status"] = "failed"
            entry["result_count"] = 0
            entry["error_code"] = code
            entry["error_message"] = message[:220]

        for source_type, details in per_source.items():
            query_id = f"{agent_id}-{source_type}-{uuid.uuid4().hex[:8]}"
            query_summary = details.get("query_summary") or f"{source_type} query by {agent_name}"
            await self.trace_emitter.emit_data_source_query_start(
                agent_id=agent_id,
                agent_name=agent_name,
                source_type=source_type,
                query_summary=query_summary,
                query_id=query_id,
                query_type="read",
            )
            latency_ms = max(
                0,
                int((now - self._agent_started_at.get(agent_id, now)).total_seconds() * 1000),
            )
            if details.get("status") == "failed":
                await self.trace_emitter.emit_data_source_query_failed(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    source_type=source_type,
                    error_code=str(details.get("error_code") or "SOURCE_QUERY_ERROR"),
                    error_message=str(details.get("error_message") or "Source query failed"),
                    latency_ms=latency_ms,
                    query_id=query_id,
                    query_summary=query_summary,
                )
            else:
                result_count = int(details.get("result_count") or 0)
                await self.trace_emitter.emit_data_source_query_complete(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    source_type=source_type,
                    result_count=result_count,
                    latency_ms=latency_ms,
                    query_id=query_id,
                    query_summary=query_summary,
                )
                await self.trace_emitter.emit_agent_evidence(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    source_type=source_type,
                    summary=f"{source_type} evidence returned {result_count} rows",
                    result_count=result_count,
                    confidence=1.0 if result_count > 0 else 0.0,
                )

    async def _emit_query_starts(self, agent_id: str, objective: str):
        if not self.trace_emitter:
            return
        profile = self._get_agent_profile(agent_id)
        if not profile or not profile.data_sources:
            return

        if self._is_actual_data_source_trace_mode():
            self._active_query_contexts[agent_id] = {
                "started_at": datetime.now(timezone.utc),
                "objective": objective,
                "queries": [],
            }
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
        if self._is_actual_data_source_trace_mode():
            self._active_query_contexts.pop(agent_id, None)
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

    def _effective_execution_timeout(self) -> int:
        """Scale execution timeout for LLM-directed mode based on agent count.

        Each agent round-trip (coordinator → specialist → coordinator) involves
        multiple real LLM calls. The base 600s budget is too tight when 5+ agents
        are in play with real Azure OpenAI latency. The timeout must also cover
        the streaming loop's idle-detection window (max_idle_loops × stream_timeout)
        so the outer timeout never preempts the inner idle break.
        """
        base = self._deterministic_execution_timeout_seconds
        if not self._is_llm_directed_mode():
            return base
        configured_budget = int(os.getenv("LLM_DIRECTED_EXECUTION_BUDGET_SECONDS", "170"))
        return max(90, min(configured_budget, 175))

    async def _execute_workflow_with_events(self, input_message: str) -> Dict[str, Any]:
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                if self._is_bounded_orchestration_mode():
                    return await asyncio.wait_for(
                        self._stream_workflow(input_message),
                        timeout=self._effective_execution_timeout(),
                    )
                return await self._stream_workflow(input_message)
            except asyncio.TimeoutError as exc:
                if self._is_bounded_orchestration_mode():
                    timeout_reason = (
                        "llm_directed_execution_timeout"
                        if self._is_llm_directed_mode()
                        else "deterministic_execution_timeout"
                    )
                    fallback = self._build_concrete_fallback_result(reason=timeout_reason)
                    await self.emit_event(
                        "workflow.status",
                        {
                            "status": "sop_concrete_fallback",
                            "reason": timeout_reason,
                            "workflowState": "COMPLETED",
                            "timeoutSeconds": self._effective_execution_timeout(),
                            "orchestration_mode": self.orchestration_mode,
                            **self._context_quality_metrics(),
                        },
                    )
                    return fallback
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
                    if isinstance(exc, RuntimeError) and str(exc) in RUNTIME_FAILURE_REASON_CODES:
                        failure_reason = str(exc)
                    else:
                        failure_reason = (
                            "llm_directed_execution_error"
                            if self._is_llm_directed_mode()
                            else "deterministic_execution_error"
                        )
                    if failure_reason in RUNTIME_FAILURE_REASON_CODES:
                        fallback = self._build_concrete_fallback_result(reason=failure_reason)
                        await self.emit_event(
                            "workflow.status",
                            {
                                "status": "sop_concrete_fallback",
                                "reason": failure_reason,
                                "workflowState": "COMPLETED",
                                "orchestration_mode": self.orchestration_mode,
                                **self._context_quality_metrics(),
                            },
                        )
                        return fallback
                    await self.emit_event(
                        "workflow.failed",
                        {
                            "error": str(exc),
                            "reason": failure_reason,
                            "workflowState": "FAILED",
                            "orchestration_mode": self.orchestration_mode,
                            "coordinator_control_output_detected": self._coordinator_control_output_detected,
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
        self._agent_invocation_counts.clear()
        self._invocation_should_respond.clear()
        self._agent_execution_counts.clear()
        self._executor_invocations_total = 0
        self._active_query_contexts.clear()
        self._last_executor_id = None
        self._coordinator_artifacts_emitted = False
        self._agent_stream_update_counts.clear()
        self._agent_stream_last_update_at.clear()
        self._agent_stream_guarded_invocation_keys.clear()
        self._streaming_text_accum.clear()
        self._handoff_specialist_snapshots.clear()
        self._specialist_findings_map.clear()
        self._latest_coordinator_artifacts.clear()
        self._latest_coordinator_response_text = ""
        self._coordinator_control_output_detected = False
        self._phase_lock_enabled = False
        self._phase_transition_time_ms = None
        self._synthesis_trigger_reason = ""
        self._fallback_mode = "none"
        self._final_confidence_level = "medium"
        self._final_assumptions = []
        logger.info("workflow_state_reset", run_id=self.run_id)

    async def _emit_synthetic_agent_completion(self, agent_id: str, reason: str):
        """Emit a synthetic completion event for an agent whose stream stalled.

        This keeps deterministic workflows moving forward when an agent never sends
        a terminal run message.
        """
        profile = self._get_agent_profile(agent_id)
        agent_name = profile.agent_name if profile else agent_id
        invocation_count = self._current_invocation_count(agent_id) or 1
        real_execution_count = self._agent_execution_counts.get(agent_id, 0)
        guard_key = self._invocation_guard_key(agent_id, invocation_count)
        self._agent_stream_guarded_invocation_keys.add(guard_key)
        self._active_agent_ids.discard(agent_id)
        self._completed_agent_ids.add(agent_id)
        started_at = self._agent_started_at.get(agent_id, datetime.now(timezone.utc))
        ended_at = datetime.now(timezone.utc)
        duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        self._agent_progress_pct[agent_id] = 100.0
        self._agent_stream_update_counts.pop(agent_id, None)
        self._agent_stream_last_update_at.pop(agent_id, None)

        # Use accumulated streaming text for the summary if available
        synth_text = "".join(self._streaming_text_accum.get(agent_id, []))[:500]
        summary_msg = synth_text if synth_text else f"{agent_name} completed via synthetic timeout guard."

        await self.emit_event(
            "executor.completed",
            {
                "executor_id": agent_id,
                "executor_name": agent_name,
                "agentId": agent_id,
                "agentName": agent_name,
                "status": "completed",
                "executionCount": invocation_count,
                "realExecutionCount": real_execution_count,
                "completionReason": "stream_timeout",
                "terminationReason": reason,
            },
        )
        await self.emit_event(
            "agent.completed",
            {
                "agentId": agent_id,
                "agentName": agent_name,
                "agent_name": agent_name,
                "message_count": len(self._streaming_text_accum.get(agent_id, [])),
                "summary": summary_msg,
                "status": "completed",
                "completionReason": "stream_timeout",
                "terminationReason": reason,
                "startedAt": started_at.isoformat(),
                "endedAt": ended_at.isoformat(),
                "durationMs": duration_ms,
                "executionCount": invocation_count,
                "realExecutionCount": real_execution_count,
            },
        )
        if self.trace_emitter:
            await self.trace_emitter.emit_span_ended(
                agent_id=agent_id,
                agent_name=agent_name,
                success=True,
                result_summary=summary_msg,
            )
        if synth_text and self._is_specialist_executor_id(agent_id):
            self.evidence.append({
                "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                "type": "agent_response",
                "agent": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        await self._emit_query_completions_and_evidence(
            agent_id=agent_id,
            response_text=summary_msg,
            message_count=len(self._streaming_text_accum.get(agent_id, [])),
        )
        await self._emit_progress(f"agent_completed:{agent_id}")

    async def _emit_synthetic_completion_if_stalled(self, agent_id: str, reason: str):
        invocation_count = self._current_invocation_count(agent_id)
        guard_key = self._invocation_guard_key(agent_id, invocation_count)
        if agent_id in self._completed_agent_ids:
            return
        if guard_key in self._agent_stream_guarded_invocation_keys:
            self._active_agent_ids.discard(agent_id)
            return
        await self._emit_synthetic_agent_completion(agent_id=agent_id, reason=reason)

    async def _check_stalled_streaming_agents(self, now: Optional[datetime] = None):
        if not self._active_agent_ids:
            return

        # Use mode-specific timeout
        if self._is_deterministic_mode():
            stall_timeout = self._deterministic_stream_timeout_seconds
        else:
            stall_timeout = self._llm_directed_stream_timeout_seconds

        now = now or datetime.now(timezone.utc)
        for agent_id in list(self._active_agent_ids):
            invocation_count = self._current_invocation_count(agent_id)
            guard_key = self._invocation_guard_key(agent_id, invocation_count)
            if guard_key in self._agent_stream_guarded_invocation_keys:
                self._active_agent_ids.discard(agent_id)
                continue

            last_update_at = self._agent_stream_last_update_at.get(agent_id)
            if not last_update_at:
                continue
            inactivity_seconds = (now - last_update_at).total_seconds()
            if inactivity_seconds >= stall_timeout:
                update_count = self._agent_stream_update_counts.get(agent_id, 0)
                if update_count >= self._deterministic_stream_update_limit:
                    logger.warning(
                        "agent_stream_update_limit_reached",
                        run_id=self.run_id,
                        agent_id=agent_id,
                        updates=update_count,
                        limit=self._deterministic_stream_update_limit,
                    )
                    reason = "stream_update_limit"
                else:
                    reason = "stream_timeout"

                mode_label = "deterministic" if self._is_deterministic_mode() else "llm_directed"
                logger.warning(
                    "agent_stream_update_timeout",
                    run_id=self.run_id,
                    agent_id=agent_id,
                    timeout_seconds=stall_timeout,
                    mode=mode_label,
                )
                await self._emit_synthetic_completion_if_stalled(
                    agent_id=agent_id,
                    reason=reason,
                )

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
        stream_timeout_seconds = (
            max(self._deterministic_stream_timeout_seconds, 180)
            if self._is_deterministic_mode()
            else min(90, max(60, self._effective_execution_timeout() // 4))
        )
        max_idle_loops = 3 if self._is_deterministic_mode() else 2
        idle_loop_count = 0
        max_control_only_supersteps = 4 if self._is_llm_directed_mode() else 0
        control_only_superstep_streak = 0
        max_noop_invocations_without_progress = (
            max(24, len(self._specialist_agent_ids()) * 6)
            if self._is_llm_directed_mode()
            else 0
        )
        max_specialist_cycles = max(1, self._max_specialist_cycles)
        synthesis_trigger_seconds = max(30, self._synthesis_trigger_seconds)
        forced_synthesis_noop_cycles = max(6, self._forced_synthesis_noop_cycles)
        noop_invocations_since_progress = 0
        superstep_real_domain_invocations = 0
        superstep_has_substantive_specialist = False
        superstep_has_substantive_coordinator = False
        superstep_active = False
        stream_started_at = datetime.now(timezone.utc)
        required_specialists = self._required_specialist_count()
        min_contrib_for_timed_synthesis = max(1, required_specialists // 2) if required_specialists else 0
        last_coordinator_signal = self._current_substantive_coordinator_signal()
        stream_iterator = self.workflow.run_stream(input_message).__aiter__()

        try:
            while True:
                try:
                    if self._is_bounded_orchestration_mode():
                        next_event_task = asyncio.create_task(stream_iterator.__anext__())
                        done, _pending = await asyncio.wait(
                            {next_event_task},
                            timeout=stream_timeout_seconds,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if not done:
                            next_event_task.cancel()
                            with suppress(asyncio.CancelledError):
                                await next_event_task
                            raise asyncio.TimeoutError()
                        event = next_event_task.result()
                    else:
                        event = await stream_iterator.__anext__()
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    idle_loop_count += 1
                    logger.warning(
                        "workflow_stream_inactivity_timeout",
                        run_id=self.run_id,
                        idle_loop_count=idle_loop_count,
                        max_idle_loops=max_idle_loops,
                        active_agents=sorted(self._active_agent_ids),
                    )
                    await self._check_stalled_streaming_agents()

                    if self._is_bounded_orchestration_mode():
                        if not self._active_agent_ids:
                            logger.warning(
                                "workflow_stream_inactivity_no_active_agents",
                                run_id=self.run_id,
                            )
                            break
                        if idle_loop_count >= max_idle_loops:
                            logger.warning(
                                "workflow_stream_inactivity_limit_reached",
                                run_id=self.run_id,
                                active_agents=sorted(self._active_agent_ids),
                            )
                            break
                    continue

                idle_loop_count = 0
                await self._process_workflow_event(event)
                await self._check_stalled_streaming_agents()

                if (
                    self._phase_lock_enabled
                    and isinstance(event, HandoffSentEvent)
                    and self._coordinator_agent_id
                    and event.source == self._coordinator_agent_id
                ):
                    await self.emit_event(
                        "workflow.status",
                        {
                            "status": "phase_lock_handoff_blocked",
                            "workflowPhase": "phase_2_synthesis",
                            "phaseLocked": True,
                            "reason": self._synthesis_trigger_reason or "phase_lock_enabled",
                            **self._context_quality_metrics(),
                        },
                    )
                    raise _LoopCappedSignal()

                if self._is_super_step_started_event(event):
                    superstep_active = True
                    superstep_real_domain_invocations = 0
                    superstep_has_substantive_specialist = False
                    superstep_has_substantive_coordinator = False

                if isinstance(event, ExecutorInvokedEvent):
                    invoked_executor_id = event.executor_id or "unknown"
                    if (
                        self._is_domain_executor_id(invoked_executor_id)
                        and not self._is_noop_invocation(invoked_executor_id)
                    ):
                        superstep_real_domain_invocations += 1
                    if self._is_noop_invocation(invoked_executor_id):
                        noop_invocations_since_progress += 1

                if isinstance(event, WorkflowOutputEvent):
                    final_output = event.data

                # --- Capture specialist contributions from ExecutorCompletedEvent ---
                if isinstance(event, ExecutorCompletedEvent):
                    comp_executor_id = event.executor_id or "unknown"
                    if self._is_noop_invocation(comp_executor_id):
                        continue
                    # --- Diagnostic logging for specialist completion data ---
                    logger.info(
                        "executor_completed_data_inspection",
                        run_id=self.run_id,
                        executor_id=comp_executor_id,
                        data_type=type(event.data).__name__ if event.data is not None else "None",
                        data_len=len(event.data) if isinstance(event.data, list) else -1,
                        data_item_types=[type(item).__name__ for item in event.data][:5] if isinstance(event.data, list) else [],
                        has_agent_response=[hasattr(item, "agent_response") for item in event.data][:5] if isinstance(event.data, list) else [],
                        agent_response_truthy=[bool(getattr(item, "agent_response", None)) for item in event.data][:5] if isinstance(event.data, list) else [],
                        streaming_accum_len=len(self._streaming_text_accum.get(comp_executor_id, [])),
                        streaming_accum_preview="".join(self._streaming_text_accum.get(comp_executor_id, []))[:200],
                    )

                    if comp_executor_id == self._coordinator_agent_id:
                        logger.info(
                            "coordinator_completed_data_inspection",
                            run_id=self.run_id,
                            data_type=type(event.data).__name__ if event.data else "None",
                            streaming_accum_keys=list(self._streaming_text_accum.keys()),
                            streaming_accum_lens={k: len(v) for k, v in self._streaming_text_accum.items()},
                        )
                        # Coordinator: extract artifacts for the plan/scoring UI
                        if not self._coordinator_artifacts_emitted:
                            coord_text, _ = self._extract_text_and_message_count_from_executor_data(event.data)
                            if not coord_text:
                                chunks = self._streaming_text_accum.get(comp_executor_id, [])
                                if chunks:
                                    coord_text = "".join(chunks)[:8000]
                            if coord_text:
                                await self._emit_coordinator_artifacts(coord_text)
                    else:
                        if not self._is_specialist_executor_id(comp_executor_id):
                            continue
                        # Specialist agent: capture as agent contribution
                        already_heard = any(r["agent"] == comp_executor_id for r in agent_responses)
                        if not already_heard:
                            resp_text, msg_count = self._extract_text_and_message_count_from_executor_data(event.data)

                            # Path B: Handoff snapshot (captured at HandoffSentEvent)
                            if not resp_text:
                                snap = self._handoff_specialist_snapshots.get(comp_executor_id, "")
                                if snap:
                                    resp_text = snap
                                    msg_count = max(1, snap.count("\n\n") + 1)

                            # Path C: Accumulated streaming text
                            if not resp_text:
                                chunks = self._streaming_text_accum.get(comp_executor_id, [])
                                if chunks:
                                    resp_text = "".join(chunks)[:8000]
                                    msg_count = len(chunks)

                            # Log extraction outcome
                            logger.info(
                                "specialist_extraction_result",
                                run_id=self.run_id,
                                executor_id=comp_executor_id,
                                extracted_len=len(resp_text),
                                msg_count=msg_count,
                                extraction_path="event_data" if msg_count > 0 and not self._streaming_text_accum.get(comp_executor_id) else ("streaming" if msg_count > 0 else "none"),
                            )

                            has_structured_findings = self._upsert_specialist_findings(comp_executor_id, resp_text)
                            if self._is_substantive_response_text(resp_text):
                                findings = self._specialist_findings_map.get(comp_executor_id, {})
                                summary_text = str(findings.get("executive_summary") or resp_text[:500]).strip()
                                agent_responses.append({
                                    "agent": comp_executor_id,
                                    "messages": msg_count,
                                    "result_summary": summary_text[:500],
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                                if has_structured_findings:
                                    superstep_has_substantive_specialist = True
                                    noop_invocations_since_progress = 0
                                self.evidence.append({
                                    "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                                    "type": "agent_response",
                                    "agent": comp_executor_id,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })

                if isinstance(event, AgentRunEvent):
                    response = event.data
                    if response is None:
                        continue
                    agent_name = event.executor_id or "unknown"
                    if self._is_noop_invocation(agent_name):
                        continue
                    if not self._is_specialist_executor_id(agent_name):
                        continue
                    if any(r["agent"] == agent_name for r in agent_responses):
                        continue
                    result_summary = ""
                    if response.messages:
                        text = self._extract_response_text(response)
                        if text:
                            result_summary = text[:500]
                    if not self._is_substantive_response_text(result_summary):
                        continue
                    has_structured_findings = self._upsert_specialist_findings(agent_name, result_summary)
                    findings = self._specialist_findings_map.get(agent_name, {})
                    agent_responses.append({
                        "agent": agent_name,
                        "messages": len(response.messages) if response.messages else 0,
                        "result_summary": str(findings.get("executive_summary") or result_summary)[:500],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    if has_structured_findings:
                        superstep_has_substantive_specialist = True
                        noop_invocations_since_progress = 0
                    self.evidence.append({
                        "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                        "type": "agent_response", "agent": agent_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # --- Accumulate streaming text from AgentRunUpdateEvent ---
                if self._is_agent_update_event(event):
                    upd_agent_id = event.executor_id or self._last_executor_id or "unknown"
                    upd_data = event.data
                    if upd_data is not None:
                        chunk = getattr(upd_data, "text", None) or ""
                        if not chunk:
                            if hasattr(upd_data, "contents"):
                                parts = []
                                for c in (upd_data.contents or []):
                                    ctype = getattr(c, "type", None)
                                    if ctype == "text":
                                        parts.append(getattr(c, "text", ""))
                                    elif ctype == "function_result":
                                        result_text = getattr(c, "result", None) or getattr(c, "text", None) or ""
                                        if isinstance(result_text, str) and result_text.strip():
                                            parts.append(result_text.strip())
                                chunk = " ".join(p for p in parts if p)
                            elif isinstance(upd_data, str):
                                chunk = upd_data
                        if chunk:
                            self._streaming_text_accum.setdefault(upd_agent_id, []).append(chunk)

                current_coordinator_signal = self._current_substantive_coordinator_signal()
                if (
                    current_coordinator_signal
                    and current_coordinator_signal != last_coordinator_signal
                ):
                    superstep_has_substantive_coordinator = True
                    noop_invocations_since_progress = 0
                    last_coordinator_signal = current_coordinator_signal

                if self._is_llm_directed_mode() and not self._phase_lock_enabled:
                    elapsed_seconds = (datetime.now(timezone.utc) - stream_started_at).total_seconds()
                    contributed = self._specialist_contribution_count()
                    repeated_specialist_cycle = any(
                        self._agent_execution_counts.get(agent_id, 0) > max_specialist_cycles
                        for agent_id in self._specialist_agent_ids()
                    )
                    all_required_contributed = (
                        required_specialists > 0 and contributed >= required_specialists
                    )
                    timed_minimum_contributed = (
                        elapsed_seconds >= synthesis_trigger_seconds
                        and contributed >= min_contrib_for_timed_synthesis
                    )
                    hard_latency_cap_reached = elapsed_seconds >= min(165, synthesis_trigger_seconds + 30)
                    forced_noop_synthesis = (
                        noop_invocations_since_progress >= forced_synthesis_noop_cycles
                        and (contributed > 0 or elapsed_seconds >= synthesis_trigger_seconds)
                    )
                    if (
                        all_required_contributed
                        or timed_minimum_contributed
                        or hard_latency_cap_reached
                        or forced_noop_synthesis
                        or repeated_specialist_cycle
                    ):
                        if all_required_contributed:
                            reason = "all_required_specialists_contributed"
                        elif timed_minimum_contributed:
                            reason = "latency_budget_threshold_reached"
                        elif hard_latency_cap_reached:
                            reason = "hard_latency_cap_reached"
                        elif forced_noop_synthesis:
                            reason = "forced_synthesis_noop_cycles"
                        else:
                            reason = "max_specialist_cycles_reached"

                        self._phase_lock_enabled = True
                        self._synthesis_trigger_reason = reason
                        self._phase_transition_time_ms = int(elapsed_seconds * 1000)
                        self._fallback_mode = "none" if all_required_contributed else "sop_concrete"
                        self._final_confidence_level = self._derive_confidence_level()
                        status = "phase_lock_enabled" if all_required_contributed else "forced_synthesis"
                        await self.emit_event(
                            "workflow.status",
                            {
                                "status": status,
                                "workflowPhase": "phase_2_synthesis",
                                "reason": reason,
                                "phaseLocked": True,
                                "specialistFindingsPacket": self._build_specialist_findings_packet(),
                                **self._context_quality_metrics(),
                            },
                        )
                        if all_required_contributed:
                            continue
                        raise _LoopCappedSignal()

                if (
                    self._is_llm_directed_mode()
                    and max_control_only_supersteps > 0
                    and self._is_super_step_completed_event(event)
                ):
                    if not superstep_active:
                        superstep_active = True
                    had_progress = (
                        superstep_real_domain_invocations > 0
                        or superstep_has_substantive_specialist
                        or superstep_has_substantive_coordinator
                    )
                    if had_progress:
                        control_only_superstep_streak = 0
                    else:
                        control_only_superstep_streak += 1
                    if control_only_superstep_streak >= max_control_only_supersteps:
                        logger.warning(
                            "workflow_control_only_superstep_streak",
                            run_id=self.run_id,
                            streak=control_only_superstep_streak,
                            max_streak=max_control_only_supersteps,
                            real_invocations_in_step=superstep_real_domain_invocations,
                            specialist_progress=superstep_has_substantive_specialist,
                            coordinator_progress=superstep_has_substantive_coordinator,
                        )
                        raise RuntimeError("insufficient_specialist_analysis")
                    superstep_real_domain_invocations = 0
                    superstep_has_substantive_specialist = False
                    superstep_has_substantive_coordinator = False
                    superstep_active = False

                if (
                    self._is_llm_directed_mode()
                    and max_noop_invocations_without_progress > 0
                    and noop_invocations_since_progress >= max_noop_invocations_without_progress
                ):
                    if not self._current_substantive_coordinator_signal():
                        self._phase_lock_enabled = True
                        self._synthesis_trigger_reason = "max_noop_invocations_without_progress"
                        self._phase_transition_time_ms = int(
                            (datetime.now(timezone.utc) - stream_started_at).total_seconds() * 1000
                        )
                        self._fallback_mode = "sop_concrete"
                        self._final_confidence_level = self._derive_confidence_level()
                        await self.emit_event(
                            "workflow.status",
                            {
                                "status": "forced_synthesis",
                                "workflowPhase": "phase_2_synthesis",
                                "reason": self._synthesis_trigger_reason,
                                "phaseLocked": True,
                                "specialistFindingsPacket": self._build_specialist_findings_packet(),
                                **self._context_quality_metrics(),
                            },
                        )
                        logger.warning(
                            "workflow_noop_invocation_streak",
                            run_id=self.run_id,
                            noop_invocations=noop_invocations_since_progress,
                            max_noop_invocations=max_noop_invocations_without_progress,
                        )
                        raise _LoopCappedSignal()
                    noop_invocations_since_progress = 0
        except _LoopCappedSignal:
            logger.info(
                "workflow_loop_capped_graceful",
                run_id=self.run_id,
                agents_heard=len(agent_responses),
            )
        finally:
            try:
                await stream_iterator.aclose()
            except Exception:
                pass
            await self._check_stalled_streaming_agents()
            if self._is_deterministic_mode():
                for agent_id in list(self._active_agent_ids):
                    if agent_id not in self._completed_agent_ids:
                        logger.warning(
                            "agent_streaming_completed_without_terminal_event",
                            run_id=self.run_id,
                            agent_id=agent_id,
                        )
                        await self._emit_synthetic_completion_if_stalled(
                            agent_id=agent_id,
                            reason="stream_completed_without_completion",
                        )

            # Sweep: capture contributions from invoked agents not yet in agent_responses
            for agent_id in list(self._agent_execution_counts.keys()):
                if not self._is_specialist_executor_id(agent_id):
                    continue
                if any(r["agent"] == agent_id for r in agent_responses):
                    continue
                # Priority: handoff snapshot > streaming text
                text = self._handoff_specialist_snapshots.get(agent_id, "")
                if not text:
                    chunks = self._streaming_text_accum.get(agent_id, [])
                    if chunks:
                        text = "".join(chunks)[:500]
                if self._is_substantive_response_text(text):
                    self._upsert_specialist_findings(agent_id, text)
                    findings = self._specialist_findings_map.get(agent_id, {})
                    agent_responses.append({
                        "agent": agent_id,
                        "messages": 1,
                        "result_summary": str(findings.get("executive_summary") or text)[:500],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    self.evidence.append({
                        "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                        "type": "agent_response",
                        "agent": agent_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            if self._should_fail_coordinator_no_specialist_handoff(
                artifacts=self._latest_coordinator_artifacts,
                agent_responses=agent_responses,
            ):
                raise RuntimeError("coordinator_no_specialist_handoff")

            if (
                self._is_bounded_orchestration_mode()
                and not self._has_specialist_participation(agent_responses)
            ):
                coordinator_answer = str(
                    self._latest_coordinator_artifacts.get("finalAnswer")
                    or self._latest_coordinator_artifacts.get("summary")
                    or self._latest_coordinator_response_text
                    or ""
                ).strip()
                if not self._is_substantive_response_text(coordinator_answer):
                    raise RuntimeError("insufficient_specialist_analysis")

            # Guarantee a coordinator.plan event reaches the UI
            if not self._coordinator_artifacts_emitted and self._is_bounded_orchestration_mode():
                summary = self._build_fused_summary(agent_responses)
                fallback_result = self._build_concrete_fallback_result(
                    reason=self._synthesis_trigger_reason or "coordinator_artifacts_missing",
                    agent_responses=agent_responses,
                    fused_summary=summary,
                )
                fallback_artifacts = {
                    "criteria": fallback_result.get("criteria", DEFAULT_RECOVERY_CRITERIA.copy()),
                    "options": fallback_result.get("options", []),
                    "timeline": fallback_result.get("timeline", []),
                    "selectedOptionId": fallback_result.get("selectedOptionId", ""),
                    "summary": fallback_result.get("summary", summary),
                    "finalAnswer": fallback_result.get("finalAnswer", fallback_result.get("answer", "")),
                }
                await self.emit_event("coordinator.plan", {
                    "selectedOptionId": fallback_artifacts["selectedOptionId"],
                    "timeline": fallback_artifacts["timeline"],
                    "summary": fallback_artifacts["summary"],
                    "finalAnswer": fallback_artifacts["finalAnswer"],
                    "options": fallback_artifacts["options"],
                })
                self._latest_coordinator_artifacts = fallback_artifacts
                self._coordinator_artifacts_emitted = True
                logger.info(
                    "fallback_coordinator_plan_emitted",
                    run_id=self.run_id,
                    agents_heard=len(agent_responses),
                )

        fused_summary = self._build_fused_summary(agent_responses)
        artifacts = self._latest_coordinator_artifacts.copy() if self._latest_coordinator_artifacts else {}
        if not artifacts and self._latest_coordinator_response_text:
            artifacts = self._parse_coordinator_artifacts(self._latest_coordinator_response_text)

        if isinstance(final_output, dict):
            result: Dict[str, Any] = dict(final_output)
        else:
            result = {}

        result.setdefault("status", "completed")
        result.setdefault("scenario", self.scenario)
        result.setdefault("agent_responses", agent_responses)
        result.setdefault("evidence_count", len(self.evidence))
        if "summary" not in result or not str(result.get("summary") or "").strip():
            result["summary"] = fused_summary

        for key in (
            "criteria",
            "options",
            "timeline",
            "selectedOptionId",
            "finalAnswer",
            "confidence",
            "assumptions",
            "evidenceCoverage",
        ):
            if key not in artifacts:
                continue
            current_value = result.get(key)
            is_empty_string = isinstance(current_value, str) and not current_value.strip()
            is_empty_list = isinstance(current_value, list) and len(current_value) == 0
            if key not in result or current_value is None or is_empty_string or is_empty_list:
                result[key] = artifacts[key]

        result["answer"] = self._resolve_final_answer(
            final_output=result,
            artifacts=artifacts,
            agent_responses=agent_responses,
            fused_summary=fused_summary,
        )

        required_specialists = self._required_specialist_count()
        contributed_specialists = self._specialist_contribution_count()
        if self._fallback_mode == "none" and (contributed_specialists < required_specialists):
            self._fallback_mode = "sop_concrete"
        self._final_confidence_level = self._derive_confidence_level()
        result["status"] = "completed"
        result.setdefault("isFallback", self._fallback_mode != "none")
        result.setdefault("fallbackMode", self._fallback_mode)
        result.setdefault("confidence", self._final_confidence_level)
        result.setdefault("assumptions", list(self._final_assumptions))
        if self._synthesis_trigger_reason and not str(result.get("reason") or "").strip():
            result["reason"] = self._synthesis_trigger_reason
        result.setdefault(
            "evidenceCoverage",
            {
                "required": required_specialists,
                "contributed": contributed_specialists,
            },
        )
        result.setdefault("specialistFindings", self._specialist_findings_map.copy())
        if (
            not self._is_substantive_response_text(str(result.get("answer") or ""))
            or not self._is_substantive_response_text(str(result.get("finalAnswer") or ""))
        ):
            concrete = self._build_concrete_fallback_result(
                reason=self._synthesis_trigger_reason or "insufficient_final_answer",
                agent_responses=agent_responses,
                fused_summary=fused_summary,
            )
            result.update(concrete)

        return result

    async def _process_workflow_event(self, event: WorkflowEvent):
        # Log every event type flowing through (debug level to avoid noise)
        evt_cls = type(event).__name__
        executor_id_log = getattr(event, "executor_id", None)
        logger.debug(
            "workflow_event_received",
            run_id=self.run_id,
            event_class=evt_cls,
            executor_id=executor_id_log or "n/a",
        )

        event_data = {
            "event_class": evt_cls,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(event, WorkflowStartedEvent):
            event_data["status"] = "started"
            await self.emit_event("workflow.started", event_data)
            await self._emit_progress("workflow_started")
            return

        if isinstance(event, ExecutorInvokedEvent):
            executor_id = event.executor_id or "unknown"
            profile = self._get_agent_profile(executor_id)
            agent_name = profile.agent_name if profile else executor_id
            invocation_count = self._agent_invocation_counts.get(executor_id, 0) + 1
            self._agent_invocation_counts[executor_id] = invocation_count
            should_respond = self._extract_should_respond_flag(event.data)
            is_noop_invocation = should_respond is False
            guard_key = self._invocation_guard_key(executor_id, invocation_count=invocation_count)
            self._invocation_should_respond[guard_key] = not is_noop_invocation

            is_real_invocation = self._is_domain_executor_id(executor_id) and not is_noop_invocation
            if is_real_invocation:
                self._executor_invocations_total += 1
                real_execution_count = self._agent_execution_counts.get(executor_id, 0) + 1
                self._agent_execution_counts[executor_id] = real_execution_count
            else:
                real_execution_count = self._agent_execution_counts.get(executor_id, 0)

            objective = "Analyze disruption state and produce evidence-backed findings"
            if profile:
                objective = (
                    f"Analyze {self.scenario.replace('_', ' ')} using {', '.join(profile.data_sources) or 'domain tools'}"
                )

            if (
                is_real_invocation
                and
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
                            "workflowPhase": "phase_2_synthesis",
                            **self._context_quality_metrics(),
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

            await self.emit_event(
                "executor.invoked",
                {
                    **event_data,
                    "executor_id": executor_id,
                    "executor_name": agent_name,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "executionCount": invocation_count,
                    "realExecutionCount": real_execution_count,
                    "shouldRespond": should_respond,
                    "isNoOpInvocation": is_noop_invocation,
                },
            )

            if not is_real_invocation:
                await self._emit_progress(f"executor_invoked:{executor_id}")
                return

            now = datetime.now(timezone.utc)
            self._agent_started_at[executor_id] = now
            if self._is_bounded_orchestration_mode():
                self._agent_stream_update_counts[executor_id] = 0
                self._agent_stream_last_update_at[executor_id] = now
            self._active_agent_ids.add(executor_id)
            self._completed_agent_ids.discard(executor_id)  # Reset completion for re-invocations
            self._agent_progress_pct[executor_id] = max(self._agent_progress_pct.get(executor_id, 0.0), 5.0)
            await self.emit_event(
                "agent.objective",
                {
                    **event_data,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "objective": objective,
                    "currentStep": "starting_analysis",
                    "percentComplete": self._agent_progress_pct[executor_id],
                    "executionCount": invocation_count,
                    "realExecutionCount": real_execution_count,
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
            invocation_count = self._current_invocation_count(executor_id) or 1
            execution_guard_key = self._invocation_guard_key(executor_id, invocation_count=invocation_count)
            is_noop_invocation = self._is_noop_invocation(executor_id, invocation_count=invocation_count)
            if execution_guard_key in self._agent_stream_guarded_invocation_keys:
                self._active_agent_ids.discard(executor_id)
                return

            profile = self._get_agent_profile(executor_id)
            agent_name = profile.agent_name if profile else executor_id
            real_execution_count = self._agent_execution_counts.get(executor_id, 0)

            if is_noop_invocation:
                self._active_agent_ids.discard(executor_id)
                await self.emit_event(
                    "executor.completed",
                    {
                        **event_data,
                        "executor_id": executor_id,
                        "executor_name": agent_name,
                        "agentId": executor_id,
                        "agentName": agent_name,
                        "status": "noop_completed",
                        "executionCount": invocation_count,
                        "realExecutionCount": real_execution_count,
                        "shouldRespond": False,
                        "isNoOpInvocation": True,
                    },
                )
                await self._emit_progress(f"executor_completed:{executor_id}")
                return

            # Skip re-emission if AgentRunEvent already completed this agent
            if executor_id in self._completed_agent_ids:
                # AgentRunEvent already emitted agent.completed with real content.
                # Still emit executor.completed lifecycle event but skip agent.completed.
                self._active_agent_ids.discard(executor_id)
                await self.emit_event(
                    "executor.completed",
                    {
                        **event_data,
                        "executor_id": executor_id,
                        "executor_name": agent_name,
                        "agentId": executor_id,
                        "agentName": agent_name,
                        "status": "completed",
                        "executionCount": invocation_count,
                        "realExecutionCount": real_execution_count,
                        "shouldRespond": True,
                        "isNoOpInvocation": False,
                    },
                )
                await self._emit_progress(f"executor_completed:{executor_id}")
                return

            self._active_agent_ids.discard(executor_id)
            started_at = self._agent_started_at.get(executor_id, datetime.now(timezone.utc))
            ended_at = datetime.now(timezone.utc)
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
            self._agent_progress_pct[executor_id] = 100.0
            execution_count = invocation_count

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
                    "realExecutionCount": real_execution_count,
                    "shouldRespond": True,
                    "isNoOpInvocation": False,
                },
            )

            if self._is_domain_executor_id(executor_id):
                self._completed_agent_ids.add(executor_id)

            logger.debug(
                "executor_completed_data_inspection",
                run_id=self.run_id,
                executor_id=executor_id,
                data_type=type(event.data).__name__ if event.data is not None else "None",
                data_repr=repr(event.data)[:200] if event.data is not None else "None",
                streaming_chunks=len(self._streaming_text_accum.get(executor_id, [])),
            )

            # Extract real content from all supported completion payload shapes.
            resp_text, msg_count = self._extract_text_and_message_count_from_executor_data(event.data)

            # Fallback: handoff snapshot > accumulated streaming text
            if not resp_text:
                resp_text = self._handoff_specialist_snapshots.get(executor_id, "")
                if resp_text:
                    msg_count = max(1, resp_text.count("\n\n") + 1)
            if not resp_text:
                chunks = self._streaming_text_accum.get(executor_id, [])
                if chunks:
                    resp_text = "".join(chunks)[:8000]
                    msg_count = len(chunks)

            summary = resp_text[:500] if resp_text else f"{agent_name} completed execution."
            if not self._is_domain_executor_id(executor_id):
                await self._emit_progress(f"executor_completed:{executor_id}")
                return

            await self.emit_event(
                "agent.completed",
                {
                    **event_data,
                    "agentId": executor_id,
                    "agentName": agent_name,
                    "agent_name": agent_name,
                    "message_count": msg_count,
                    "summary": summary,
                    "status": "completed",
                    "completionReason": "executor_completed",
                    "startedAt": started_at.isoformat(),
                    "endedAt": ended_at.isoformat(),
                    "durationMs": duration_ms,
                    "executionCount": execution_count,
                    "realExecutionCount": real_execution_count,
                },
            )
            if self.trace_emitter:
                await self.trace_emitter.emit_span_ended(
                    agent_id=executor_id,
                    agent_name=agent_name,
                    success=True,
                    result_summary=summary,
                )
            await self._emit_query_completions_and_evidence(
                agent_id=executor_id,
                response_text=summary,
                message_count=msg_count,
            )

            await self._emit_progress(f"executor_completed:{executor_id}")
            return

        if isinstance(event, AgentRunEvent):
            response = event.data
            if response is None:
                return
            agent_id = event.executor_id or "unknown"
            invocation_count = self._current_invocation_count(agent_id) or 1
            execution_count = self._agent_execution_counts.get(agent_id, 0)
            execution_guard_key = self._invocation_guard_key(agent_id, invocation_count=invocation_count)
            if execution_guard_key in self._agent_stream_guarded_invocation_keys:
                self._active_agent_ids.discard(agent_id)
                return
            if self._is_noop_invocation(agent_id, invocation_count=invocation_count):
                self._active_agent_ids.discard(agent_id)
                return
            profile = self._get_agent_profile(agent_id)
            agent_name = profile.agent_name if profile else agent_id
            response_text = self._extract_response_text(response)
            message_count = len(response.messages) if response.messages else 0

            logger.info(
                "agent_run_event_captured",
                run_id=self.run_id,
                agent_id=agent_id,
                message_count=message_count,
                text_length=len(response_text),
            )

            started_at = self._agent_started_at.get(agent_id, datetime.now(timezone.utc))
            ended_at = datetime.now(timezone.utc)
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
            self._active_agent_ids.discard(agent_id)
            self._agent_progress_pct[agent_id] = 100.0

            if self._is_domain_executor_id(agent_id):
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
                    "executionCount": invocation_count,
                    "realExecutionCount": execution_count,
                },
            )

            if self.trace_emitter:
                await self.trace_emitter.emit_span_ended(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    success=True,
                    result_summary=response_text[:220] or "Analysis complete",
                )

            if self._is_domain_executor_id(agent_id):
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

        if isinstance(event, AgentRunUpdateEvent) or self._is_agent_update_event(event):
            executor_id = event.executor_id or self._last_executor_id or "unknown"
            invocation_count = self._current_invocation_count(executor_id)
            execution_guard_key = self._invocation_guard_key(executor_id, invocation_count=invocation_count)

            if execution_guard_key in self._agent_stream_guarded_invocation_keys:
                self._active_agent_ids.discard(executor_id)
                return
            if self._is_noop_invocation(executor_id, invocation_count=invocation_count):
                self._active_agent_ids.discard(executor_id)
                return
            if not self._is_domain_executor_id(executor_id):
                self._active_agent_ids.discard(executor_id)
                return
            profile = self._get_agent_profile(executor_id)
            agent_name = profile.agent_name if profile else executor_id
            next_progress = min(92.0, self._agent_progress_pct.get(executor_id, 5.0) + 8.0)
            self._agent_progress_pct[executor_id] = next_progress
            self._active_agent_ids.add(executor_id)
            now = datetime.now(timezone.utc)
            if self._is_bounded_orchestration_mode():
                update_count = self._agent_stream_update_counts.get(executor_id, 0) + 1
                self._agent_stream_update_counts[executor_id] = update_count
                self._agent_stream_last_update_at[executor_id] = now

            # Accumulate streaming text for later use by completion handlers
            upd_data = event.data
            if upd_data is not None:
                chunk = getattr(upd_data, "text", None) or ""
                if not chunk and hasattr(upd_data, "contents"):
                    # Extract text AND function_result content (tool output)
                    parts = []
                    for c in (upd_data.contents or []):
                        ctype = getattr(c, "type", None)
                        if ctype == "text":
                            parts.append(getattr(c, "text", ""))
                        elif ctype == "function_result":
                            # Tool output — parse structured payload for real source tracing.
                            raw_result = getattr(c, "result", None)
                            if raw_result is None:
                                raw_result = getattr(c, "text", None)
                            parsed_payload = self._parse_possible_json_payload(raw_result)
                            if parsed_payload and self._is_actual_data_source_trace_mode():
                                await self._emit_real_data_source_events_from_tool_payload(
                                    agent_id=executor_id,
                                    payload=parsed_payload,
                                )
                            result_text = raw_result if isinstance(raw_result, str) else json.dumps(raw_result, ensure_ascii=True) if raw_result is not None else ""
                            if isinstance(result_text, str) and result_text.strip():
                                parts.append(result_text.strip())
                    chunk = " ".join(p for p in parts if p)
                if chunk:
                    self._streaming_text_accum.setdefault(executor_id, []).append(chunk)
                    chunks_so_far = len(self._streaming_text_accum.get(executor_id, []))
                    if chunks_so_far == 1:
                        logger.info(
                            "streaming_text_first_chunk",
                            run_id=self.run_id,
                            executor_id=executor_id,
                            chunk_len=len(chunk),
                            chunk_preview=chunk[:100],
                        )
                    elif chunks_so_far % 10 == 0:
                        logger.debug(
                            "streaming_text_accumulated",
                            run_id=self.run_id,
                            executor_id=executor_id,
                            total_chunks=chunks_so_far,
                            chunk_len=len(chunk),
                        )

            # Throttle: emit at most one consolidated event per _stream_throttle_td per agent
            last_emit = self._agent_stream_throttle_at.get(executor_id)
            if last_emit and (now - last_emit) < self._stream_throttle_td:
                # Under throttle window — skip all emits, just track progress internally
                pass
            else:
                self._agent_stream_throttle_at[executor_id] = now
                await self.emit_event(
                    "agent.progress",
                    {
                        **event_data,
                        "agentId": executor_id,
                        "agentName": agent_name,
                        "percentComplete": next_progress,
                        "currentStep": "streaming_analysis",
                        "executionCount": invocation_count,
                        "realExecutionCount": self._agent_execution_counts.get(executor_id, 0),
                    },
                )
            return

        if isinstance(event, HandoffSentEvent):
            source_id = event.source
            target_id = event.target
            # Snapshot streaming text at handoff time for non-coordinator agents
            if source_id != self._coordinator_agent_id:
                chunks = self._streaming_text_accum.get(source_id, [])
                if chunks:
                    self._handoff_specialist_snapshots[source_id] = "".join(chunks)[:8000]
                    logger.info(
                        "handoff_specialist_snapshot_captured",
                        run_id=self.run_id,
                        source=source_id,
                        target=target_id,
                        snapshot_len=len(self._handoff_specialist_snapshots[source_id]),
                    )
                else:
                    logger.warning(
                        "handoff_specialist_snapshot_empty",
                        run_id=self.run_id,
                        source=source_id,
                        target=target_id,
                    )
            if self.trace_emitter:
                await self.trace_emitter.emit_handover(
                    from_agent=source_id,
                    to_agent=target_id,
                    reason="Specialist completed analysis, returning to coordinator",
                )
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
