"""
Event emission middleware for Agent Framework agents.
Includes event emission wrapper and evidence collection.
"""

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from agent_framework import ChatAgent
import structlog

from telemetry import get_tracer, traced_span

logger = structlog.get_logger()

_tracer = get_tracer("agent")


class AgentEventEmitter:
    """Wrapper that adds event emission to ChatAgent runs."""

    def __init__(self, agent: ChatAgent, event_callback: Callable, run_id: str, agent_id: Optional[str] = None):
        self.agent = agent
        self.event_callback = event_callback
        self.run_id = run_id
        self.agent_id = agent_id or getattr(agent, 'name', 'unknown_agent')
        self.evidence: List[Dict[str, Any]] = []

    async def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        if self.event_callback:
            await self.event_callback(
                event_type=event_type,
                payload={
                    "run_id": self.run_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent_id": self.agent_id,
                    "agent_name": getattr(self.agent, 'name', self.agent_id),
                    **payload,
                }
            )

    async def run(self, message: str, **kwargs) -> str:
        """Run the agent with event emission and OTel tracing."""
        with traced_span(_tracer, f"agent.run.{self.agent_id}"):
            return await self._run_inner(message, **kwargs)

    async def _run_inner(self, message: str, **kwargs) -> str:
        started_at = datetime.utcnow()
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"

        await self._emit_event("agent.status", {
            "execution_id": execution_id,
            "status": "running",
            "current_objective": message[:200],
            "progress": 0.0,
        })

        try:
            response = await self.agent.run(message, **kwargs)
            response_text = str(response)

            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            self.evidence.append({
                "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                "agent_id": self.agent_id,
                "timestamp": datetime.utcnow().isoformat(),
                "type": "insight",
                "summary": f"Completed objective: {message[:100]}",
                "details": {"response_length": len(response_text)},
            })

            await self._emit_event("agent.status", {
                "execution_id": execution_id,
                "status": "completed",
                "duration_ms": duration_ms,
                "progress": 1.0,
            })

            return response_text

        except Exception as e:
            await self._emit_event("agent.status", {
                "execution_id": execution_id,
                "status": "failed",
                "error": str(e),
            })
            raise


class EvidenceCollector:
    """Collects and aggregates evidence from multiple agents."""

    def __init__(self):
        self.evidence: List[Dict[str, Any]] = []

    def add_evidence(self, ev: Dict[str, Any]):
        self.evidence.append(ev)

    def get_evidence(self) -> List[Dict[str, Any]]:
        return self.evidence.copy()

    def get_evidence_by_agent(self, agent_id: str) -> List[Dict[str, Any]]:
        return [ev for ev in self.evidence if ev.get("agent_id") == agent_id]

    def clear(self):
        self.evidence = []


class EvidenceContextProvider:
    """
    Context provider that injects accumulated evidence into agent calls.
    Allows agents to access evidence from previous agents in the workflow.
    """

    def __init__(self, evidence_collector: EvidenceCollector, max_evidence: int = 10):
        self.evidence_collector = evidence_collector
        self.max_evidence = max_evidence

    async def invoking(self, messages: List[Any], **kwargs) -> Dict[str, Any]:
        """Called before agent invocation - inject evidence context."""
        evidence = self.evidence_collector.get_evidence()
        if not evidence:
            return {}

        recent_evidence = evidence[-self.max_evidence:]
        evidence_text = "\n".join([
            f"- [{ev.get('type', 'unknown')}] {ev.get('summary', 'No summary')} "
            f"(from {ev.get('agent_id', 'unknown')})"
            for ev in recent_evidence
        ])

        return {
            "instructions": f"\n## Previous Analysis Evidence\n{evidence_text}\n"
        }

    async def invoked(self, request_messages: List[Any], response_messages: Optional[List[Any]] = None, **kwargs) -> None:
        """Called after agent invocation — extract tool results and collect evidence."""
        if not response_messages:
            return
        for msg in response_messages:
            # Collect tool call results as evidence
            tool_name = getattr(msg, 'tool_name', None) or getattr(msg, 'name', None)
            if tool_name:
                content = getattr(msg, 'content', None)
                summary = str(content)[:200] if content else "No content"
                # Infer data source from tool name
                source_type = "unknown"
                if any(kw in tool_name for kw in ("sql", "flight", "crew", "fleet", "mel", "passenger")):
                    source_type = "SQL"
                elif any(kw in tool_name for kw in ("kql", "live_position", "sigmet", "pirep")):
                    source_type = "KQL"
                elif any(kw in tool_name for kw in ("graph", "network", "route")):
                    source_type = "GRAPH"
                elif any(kw in tool_name for kw in ("asrs", "search_similar", "precedent")):
                    source_type = "VECTOR_OPS"
                elif any(kw in tool_name for kw in ("regulation", "compliance", "far117")):
                    source_type = "VECTOR_REG"
                elif any(kw in tool_name for kw in ("notam", "cosmos")):
                    source_type = "NOSQL"
                elif any(kw in tool_name for kw in ("fabric", "bts", "historical_delay")):
                    source_type = "FABRIC_SQL"

                self.evidence_collector.add_evidence({
                    "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
                    "agent_id": "unknown",
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": "tool_result",
                    "summary": f"[{tool_name}] {summary}",
                    "source_type": source_type,
                    "tool_name": tool_name,
                })
