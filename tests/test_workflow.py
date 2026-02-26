"""
Tests for workflow builder and orchestrator engine instantiation.
"""

import pytest
from orchestrator.workflows import WorkflowType
from orchestrator.engine import OrchestratorEngine, OrchestratorDecision
from orchestrator.trace_emitter import TraceEmitter
from orchestrator.middleware import EvidenceCollector, EvidenceContextProvider
from orchestrator.workflows import OrchestrationMode


class TestWorkflowType:
    def test_sequential_type(self):
        assert WorkflowType.SEQUENTIAL == "sequential"

    def test_handoff_type(self):
        assert WorkflowType.HANDOFF == "handoff"


class TestOrchestratorEngine:
    def test_engine_initialization(self):
        engine = OrchestratorEngine(
            run_id="test-run-123",
            workflow_type=WorkflowType.SEQUENTIAL,
        )
        assert engine.run_id == "test-run-123"
        assert engine.workflow_type == WorkflowType.SEQUENTIAL
        assert engine.decisions == []
        assert engine.evidence == []
        assert engine.checkpoint_storage is not None

    def test_handoff_defaults_to_llm_directed_mode(self):
        engine = OrchestratorEngine(
            run_id="test-run-handoff-default",
            workflow_type=WorkflowType.HANDOFF,
        )
        assert engine.orchestration_mode == OrchestrationMode.LLM_DIRECTED

    def test_engine_without_checkpointing(self):
        engine = OrchestratorEngine(
            run_id="test-run",
            enable_checkpointing=False,
        )
        assert engine.checkpoint_storage is None

    def test_engine_with_event_emitter(self):
        from unittest.mock import AsyncMock
        callback = AsyncMock()
        engine = OrchestratorEngine(
            run_id="test-run",
            event_emitter=callback,
        )
        assert engine.event_emitter is callback

    def test_record_decision(self):
        engine = OrchestratorEngine(run_id="test-run")
        decision = engine._record_decision(
            decision_type="include_agent",
            reasoning="Core agent required",
            confidence=0.95,
            action={"agent_id": "flight_analyst"},
        )
        assert isinstance(decision, OrchestratorDecision)
        assert decision.decision_type == "include_agent"
        assert decision.confidence == 0.95
        assert len(engine.decisions) == 1


class TestTraceEmitter:
    def test_trace_emitter_creation(self):
        async def callback(event_type: str, payload: dict):
            return None

        emitter = TraceEmitter(run_id="test-run", event_callback=callback)
        assert emitter.run_id == "test-run"

    def test_trace_emitter_with_callback(self):
        from unittest.mock import AsyncMock
        callback = AsyncMock()
        emitter = TraceEmitter(run_id="test-run", event_callback=callback)
        assert emitter.event_callback is callback


class TestEvidenceCollector:
    def test_add_and_get_evidence(self):
        collector = EvidenceCollector()
        collector.add_evidence({
            "agent_id": "flight_analyst",
            "type": "insight",
            "summary": "Test evidence",
        })
        evidence = collector.get_evidence()
        assert len(evidence) == 1
        assert evidence[0]["agent_id"] == "flight_analyst"

    def test_get_evidence_by_agent(self):
        collector = EvidenceCollector()
        collector.add_evidence({"agent_id": "flight_analyst", "summary": "a"})
        collector.add_evidence({"agent_id": "safety_inspector", "summary": "b"})
        collector.add_evidence({"agent_id": "flight_analyst", "summary": "c"})

        flight_evidence = collector.get_evidence_by_agent("flight_analyst")
        assert len(flight_evidence) == 2

    def test_clear_evidence(self):
        collector = EvidenceCollector()
        collector.add_evidence({"agent_id": "test", "summary": "test"})
        collector.clear()
        assert len(collector.get_evidence()) == 0


class TestEvidenceContextProvider:
    def test_creation(self):
        collector = EvidenceCollector()
        provider = EvidenceContextProvider(collector)
        assert provider.max_evidence == 10

    def test_custom_max_evidence(self):
        collector = EvidenceCollector()
        provider = EvidenceContextProvider(collector, max_evidence=5)
        assert provider.max_evidence == 5
