"""
Trace Event Emitter for Dynamic Orchestration.
Emits rich structured events for full UI visibility into orchestrator decisions.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import structlog

from orchestrator.agent_registry import AgentSelectionResult
from telemetry import get_current_trace_context

logger = structlog.get_logger()

SOURCE_PROVIDER_MAP: Dict[str, str] = {
    "SQL": "Azure",
    "KQL": "Fabric",
    "GRAPH": "Fabric",
    "NOSQL": "Azure",
    "FABRIC_SQL": "Fabric",
    "VECTOR_OPS": "Azure",
    "VECTOR_REG": "Azure",
    "VECTOR_AIRPORT": "Azure",
}


class TraceEmitter:
    """
    Emits rich trace events for orchestrator visibility.

    Event Types:
    - orchestrator.plan: Initial plan with selected/excluded agents
    - orchestrator.decision: Individual decisions
    - span.started / span.ended: Agent execution lifecycle
    - handover: Control transfer between agents
    - agent.activated / agent.excluded: Agent lifecycle for canvas
    - data_source.query_start / query_complete: Data source activity
    - agent.recommendation: Agent output
    - coordinator.scoring / coordinator.plan: Decision output
    - recovery.option: Individual recovery options
    """

    def __init__(
        self,
        run_id: str,
        event_callback: Callable,
        trace_id: Optional[str] = None,
    ):
        self.run_id = run_id
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:8]}"
        self.event_callback = event_callback
        self._span_stack: List[str] = []
        self._current_span_id: Optional[str] = None
        self._warned_missing_otel = False

    def _generate_span_id(self) -> str:
        return f"span-{uuid.uuid4().hex[:8]}"

    async def _emit(self, kind: str, message: str, payload: Dict[str, Any]):
        if self.event_callback:
            otel_ctx = get_current_trace_context()
            trace_id = self.trace_id
            span_id = self._current_span_id
            parent_span_id = payload.get("parentSpanId")
            if otel_ctx:
                trace_id = otel_ctx.get("trace_id") or trace_id
                span_id = otel_ctx.get("span_id") or span_id
                parent_span_id = otel_ctx.get("parent_span_id") or parent_span_id
            elif not self._warned_missing_otel:
                self._warned_missing_otel = True
                logger.warning("otel_context_missing", run_id=self.run_id, first_missing_kind=kind)

            actor = payload.get("actor")
            if not isinstance(actor, dict):
                agent_id = payload.get("agentId")
                if agent_id:
                    actor = {
                        "kind": "agent",
                        "id": agent_id,
                        "name": payload.get("agentName") or agent_id,
                    }
                else:
                    actor = {
                        "kind": "orchestrator",
                        "id": "orchestrator",
                        "name": "Orchestrator",
                    }

            await self.event_callback(
                event_type=kind,
                payload={
                    "message": message,
                    "kind": kind,
                    "traceId": trace_id,
                    "spanId": span_id,
                    "parentSpanId": parent_span_id,
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "parent_span_id": parent_span_id,
                    "actor": actor,
                    **payload,
                },
            )

    # ── Plan & decision events ────────────────────────────────────

    async def emit_plan(
        self,
        problem: str,
        selected_agents: List[AgentSelectionResult],
        excluded_agents: List[AgentSelectionResult],
    ):
        payload = {
            "selectedAgents": [
                {
                    "id": a.agent_id, "name": a.agent_name, "reason": a.reason,
                    "icon": a.icon, "color": a.color, "dataSources": a.data_sources,
                }
                for a in selected_agents
            ],
            "excludedAgents": [
                {
                    "id": a.agent_id, "name": a.agent_name, "reason": a.reason,
                    "icon": a.icon, "color": a.color, "dataSources": a.data_sources,
                }
                for a in excluded_agents
            ],
            "problemSummary": problem[:200],
            "estimatedAgentCount": len(selected_agents),
        }
        await self._emit(
            "orchestrator.plan",
            f"Execution plan created with {len(selected_agents)} agents",
            payload,
        )

    async def emit_decision(
        self,
        decision_type: str,
        reason: str,
        confidence: float = 0.9,
        inputs_considered: List[str] = None,
    ):
        payload = {
            "decisionType": decision_type,
            "reason": reason,
            "confidence": confidence,
            "inputsConsidered": inputs_considered or [],
        }
        await self._emit("orchestrator.decision", reason, payload)

    async def emit_include_agent(self, agent_id: str, agent_name: str, reason: str, inputs: List[str] = None):
        await self.emit_decision(
            decision_type="include_agent", reason=reason,
            confidence=0.95, inputs_considered=inputs or ["problem_analysis"],
        )

    async def emit_exclude_agent(self, agent_id: str, agent_name: str, reason: str, inputs: List[str] = None):
        await self.emit_decision(
            decision_type="exclude_agent", reason=reason,
            confidence=0.90, inputs_considered=inputs or ["problem_analysis"],
        )

    # ── Span lifecycle ────────────────────────────────────────────

    async def emit_span_started(self, agent_id: str, agent_name: str, objective: str) -> str:
        span_id = self._generate_span_id()
        parent_span_id = self._current_span_id
        self._span_stack.append(span_id)
        self._current_span_id = span_id

        payload = {
            "spanId": span_id, "parentSpanId": parent_span_id,
            "agentId": agent_id, "agentName": agent_name, "objective": objective,
        }
        await self._emit("span.started", f"{agent_name} starting: {objective[:50]}", payload)
        return span_id

    async def emit_span_ended(self, agent_id: str, agent_name: str, success: bool = True, result_summary: str = None):
        span_id = self._current_span_id
        if self._span_stack:
            self._span_stack.pop()
            self._current_span_id = self._span_stack[-1] if self._span_stack else None

        payload = {
            "spanId": span_id, "agentId": agent_id, "agentName": agent_name,
            "success": success, "resultSummary": result_summary,
        }
        status = "completed" if success else "failed"
        await self._emit("span.ended", f"{agent_name} {status}", payload)

    async def emit_handover(self, from_agent: str, to_agent: str, reason: str):
        payload = {"fromAgent": from_agent, "toAgent": to_agent, "reason": reason}
        await self._emit("handover", f"Handover: {from_agent} -> {to_agent}", payload)

    async def emit_agent_objective(self, agent_id: str, agent_name: str, objective: str):
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "objective": objective,
        }
        await self._emit("agent.objective", f"{agent_name} objective updated", payload)

    async def emit_agent_progress(
        self,
        agent_id: str,
        agent_name: str,
        percent_complete: float,
        current_step: str,
    ):
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "percentComplete": max(0.0, min(percent_complete, 100.0)),
            "currentStep": current_step,
        }
        await self._emit(
            "agent.progress",
            f"{agent_name} progress {payload['percentComplete']:.0f}%",
            payload,
        )

    async def emit_tool_called(
        self,
        agent_id: str,
        agent_name: str,
        tool_name: str,
        tool_id: Optional[str] = None,
        tool_input: Optional[str] = None,
    ):
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "toolName": tool_name,
            "toolId": tool_id,
            "toolInput": (tool_input or "")[:220],
        }
        await self._emit("tool.called", f"{agent_name} called {tool_name}", payload)

    async def emit_tool_completed(
        self,
        agent_id: str,
        agent_name: str,
        tool_name: str,
        latency_ms: int,
        result_count: Optional[int] = None,
        tool_id: Optional[str] = None,
    ):
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "toolName": tool_name,
            "toolId": tool_id,
            "latencyMs": latency_ms,
            "resultCount": result_count,
            "status": "completed",
        }
        await self._emit(
            "tool.completed",
            f"{agent_name} completed {tool_name} in {latency_ms}ms",
            payload,
        )

    async def emit_tool_failed(
        self,
        agent_id: str,
        agent_name: str,
        tool_name: str,
        error: str,
        tool_id: Optional[str] = None,
    ):
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "toolName": tool_name,
            "toolId": tool_id,
            "status": "failed",
            "error": error[:220],
        }
        await self._emit("tool.failed", f"{agent_name} failed {tool_name}", payload)

    # ── NEW: Agent activation/exclusion for canvas ────────────────

    async def emit_agent_activated(
        self, agent_id: str, agent_name: str, reason: str,
        data_sources: List[str] = None, icon: str = "", color: str = "",
    ):
        payload = {
            "agentId": agent_id, "agentName": agent_name, "reason": reason,
            "dataSources": data_sources or [], "icon": icon, "color": color,
        }
        await self._emit("agent.activated", f"{agent_name} activated: {reason[:60]}", payload)

    async def emit_agent_excluded(self, agent_id: str, agent_name: str, reason: str):
        payload = {"agentId": agent_id, "agentName": agent_name, "reason": reason}
        await self._emit("agent.excluded", f"{agent_name} excluded: {reason[:60]}", payload)

    # ── NEW: Data source activity ─────────────────────────────────

    async def emit_data_source_query_start(
        self,
        agent_id: str,
        agent_name: str,
        source_type: str,
        query_summary: str,
        query_id: Optional[str] = None,
        query_type: str = "read",
    ):
        provider = SOURCE_PROVIDER_MAP.get(source_type, "Unknown")
        payload = {
            "agentId": agent_id, "agentName": agent_name, "sourceType": source_type,
            "querySummary": query_summary[:200],
            "queryId": query_id,
            "queryType": query_type,
            "sourceProvider": provider,
        }
        await self._emit("data_source.query_start", f"{source_type} query started by {agent_name}", payload)

    async def emit_data_source_query_complete(
        self,
        agent_id: str,
        agent_name: str,
        source_type: str,
        result_count: int,
        latency_ms: int,
        query_id: Optional[str] = None,
        query_summary: Optional[str] = None,
    ):
        provider = SOURCE_PROVIDER_MAP.get(source_type, "Unknown")
        payload = {
            "agentId": agent_id, "agentName": agent_name, "sourceType": source_type,
            "resultCount": result_count, "latencyMs": latency_ms,
            "queryId": query_id,
            "querySummary": (query_summary or f"Retrieved evidence from {source_type}")[:200],
            "sourceProvider": provider,
        }
        await self._emit(
            "data_source.query_complete",
            f"{source_type}: {result_count} results in {latency_ms}ms",
            payload,
        )

    async def emit_agent_evidence(
        self,
        agent_id: str,
        agent_name: str,
        source_type: str,
        summary: str,
        result_count: int,
        confidence: float = 0.8,
    ):
        payload = {
            "agentId": agent_id,
            "agentName": agent_name,
            "sourceType": source_type,
            "summary": summary[:260],
            "resultCount": result_count,
            "confidence": confidence,
            "sourceProvider": SOURCE_PROVIDER_MAP.get(source_type, "Unknown"),
        }
        await self._emit(
            "agent.evidence",
            f"{agent_id} gathered {result_count} evidence items from {source_type}",
            payload,
        )

    # ── NEW: Agent recommendation ─────────────────────────────────

    async def emit_agent_recommendation(
        self, agent_id: str, agent_name: str, recommendation: str, confidence: float,
    ):
        payload = {
            "agentId": agent_id, "agentName": agent_name, "recommendation": recommendation,
            "confidence": confidence,
        }
        await self._emit(
            "agent.recommendation",
            f"{agent_id} recommendation (confidence: {confidence:.0%})",
            payload,
        )

    # ── NEW: Coordinator scoring & plan ───────────────────────────

    async def emit_coordinator_scoring(
        self,
        options: List[Dict[str, Any]],
        criteria: List[str],
        scores: Dict[str, Dict[str, float]],
    ):
        payload = {"options": options, "criteria": criteria, "scores": scores}
        await self._emit(
            "coordinator.scoring",
            f"Scored {len(options)} recovery options across {len(criteria)} criteria",
            payload,
        )

    async def emit_coordinator_plan(
        self,
        selected_option_id: str,
        timeline: List[Dict[str, Any]],
        summary: str,
    ):
        payload = {
            "selectedOptionId": selected_option_id,
            "timeline": timeline, "summary": summary,
        }
        await self._emit("coordinator.plan", summary[:100], payload)

    async def emit_recovery_option(
        self,
        option_id: str,
        description: str,
        scores: Dict[str, float],
        rank: int,
    ):
        payload = {
            "optionId": option_id, "description": description,
            "scores": scores, "rank": rank,
        }
        await self._emit(
            "recovery.option",
            f"Option #{rank}: {description[:60]}",
            payload,
        )
