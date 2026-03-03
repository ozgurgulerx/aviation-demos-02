"""Regression tests for data-source stabilization changes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agents.tools import retriever_query, retriever_query_multi, source_errors_from_citations
from data_sources.unified_retriever import AsyncUnifiedRetriever, _is_safe_read_only_sql
from orchestrator.agent_registry import AgentSelectionResult
from orchestrator.engine import OrchestratorEngine
from orchestrator.trace_emitter import TraceEmitter
import main as backend_main


def test_sql_read_only_validator_allows_select_and_cte():
    ok_select, code_select = _is_safe_read_only_sql("SELECT * FROM demo.ops_flight_legs LIMIT 1")
    ok_cte, code_cte = _is_safe_read_only_sql(
        "WITH x AS (SELECT 1 AS a) SELECT a FROM x"
    )
    ok_paren, code_paren = _is_safe_read_only_sql("(SELECT 1)")

    assert ok_select is True, code_select
    assert ok_cte is True, code_cte
    assert ok_paren is True, code_paren


def test_sql_read_only_validator_blocks_mutation_and_multi_statement():
    ok_delete, code_delete = _is_safe_read_only_sql("DELETE FROM demo.ops_flight_legs")
    ok_multi, code_multi = _is_safe_read_only_sql("SELECT 1; SELECT 2")

    assert ok_delete is False
    assert code_delete.startswith("SQL_BLOCKED_") or code_delete == "SQL_NON_READ_ONLY"
    assert ok_multi is False
    assert code_multi == "SQL_MULTI_STATEMENT"


@pytest.mark.asyncio
async def test_graph_relation_resolution_uses_visible_schema_order():
    class _FakeConn:
        async def fetchval(self, query, *args):
            if query == "SELECT to_regclass($1)::text":
                relation = args[0]
                if relation == "public.ops_graph_edges":
                    return None
                if relation == "demo.ops_graph_edges":
                    return "demo.ops_graph_edges"
                return None
            if query == "SELECT to_regclass('ops_graph_edges')::text":
                return None
            raise AssertionError(f"Unexpected query: {query}")

    retriever = AsyncUnifiedRetriever(pg_pool=object())
    retriever._sql_visible_schemas = ["public", "demo"]
    relation = await retriever._resolve_graph_edges_relation(_FakeConn())
    assert relation == "demo.ops_graph_edges"


@pytest.mark.asyncio
async def test_retriever_query_timeout_returns_explicit_error_citation():
    async def _slow():
        await asyncio.sleep(0.05)
        return [], []

    rows, citations = await retriever_query(_slow(), timeout=0)
    assert rows == []
    errors = source_errors_from_citations(citations)
    assert errors
    assert errors[0]["errorCode"] == "SOURCE_TIMEOUT"


@pytest.mark.asyncio
async def test_retriever_query_multi_error_returns_per_source_citations():
    async def _failing_query_multiple(query: str, sources: list[str]):
        raise RuntimeError("backend unavailable")

    results = await retriever_query_multi(
        _failing_query_multiple("q", ["SQL", "KQL"]),
        timeout=1,
    )
    assert set(results.keys()) == {"SQL", "KQL"}
    for source_type, (rows, citations) in results.items():
        assert rows == []
        assert citations
        errors = source_errors_from_citations(citations)
        assert errors
        assert errors[0]["sourceType"] == source_type


def test_source_errors_from_citations_ignores_query_text_keywords():
    citations = [
        {
            "source_type": "SQL",
            "title": "SQL query: SELECT * FROM demo.ops_flight_legs WHERE missing_connections > 0",
            "content_preview": "[]",
        }
    ]
    errors = source_errors_from_citations(citations)
    assert errors == []


def test_engine_infer_result_count_ignores_metadata_lists():
    engine = OrchestratorEngine(run_id="run-test-infer-count", enable_checkpointing=False)
    payload = {
        "routes": [],
        "connectivity": [],
        "citations": [{"source_type": "SQL", "title": "SQL query: SELECT 1"}],
        "sourceErrors": [],
    }
    assert engine._infer_result_count_from_payload(payload) == 0


@pytest.mark.asyncio
async def test_engine_emits_real_source_query_complete_and_failed_events():
    captured: list[tuple[str, dict]] = []

    async def _event_emitter(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="run-test-real-trace",
        event_emitter=_event_emitter,
        workflow_type="handoff",
        orchestration_mode="llm_directed",
    )
    engine.trace_emitter = TraceEmitter(run_id=engine.run_id, event_callback=_event_emitter)
    engine._agent_lookup["agent_x"] = AgentSelectionResult(
        agent_id="agent_x",
        agent_name="Agent X",
        short_name="AX",
        category="specialist",
        included=True,
        reason="test",
        conditions_evaluated=["test"],
        priority=10,
        data_sources=["SQL", "KQL"],
    )
    engine._agent_started_at["agent_x"] = datetime.now(timezone.utc) - timedelta(milliseconds=20)

    payload = {
        "count": 3,
        "citations": [
            {"source_type": "SQL", "title": "SQL query: SELECT * FROM demo.ops_flight_legs"},
            {"source_type": "KQL", "title": "KQL endpoint not configured"},
        ],
        "sourceErrors": [
            {
                "sourceType": "KQL",
                "errorCode": "SOURCE_NOT_CONFIGURED",
                "message": "KQL endpoint not configured",
                "retryable": True,
            }
        ],
    }

    await engine._emit_real_data_source_events_from_tool_payload("agent_x", payload)

    kinds = [etype for etype, _payload in captured]
    assert "data_source.query_start" in kinds
    assert "data_source.query_complete" in kinds
    assert "data_source.query_failed" in kinds

    completed = [p for k, p in captured if k == "data_source.query_complete"]
    failed = [p for k, p in captured if k == "data_source.query_failed"]
    assert any((p.get("sourceType") == "SQL" and p.get("resultCount", 0) >= 0) for p in completed)
    assert any((p.get("sourceType") == "KQL" and p.get("errorCode") == "SOURCE_NOT_CONFIGURED") for p in failed)


@pytest.mark.asyncio
async def test_engine_does_not_fail_success_citation_with_error_like_query_text():
    captured: list[tuple[str, dict]] = []

    async def _event_emitter(event_type: str, payload: dict):
        captured.append((event_type, payload))

    engine = OrchestratorEngine(
        run_id="run-test-query-text-error-words",
        event_emitter=_event_emitter,
        workflow_type="handoff",
        orchestration_mode="llm_directed",
    )
    engine.trace_emitter = TraceEmitter(run_id=engine.run_id, event_callback=_event_emitter)
    engine._agent_lookup["agent_x"] = AgentSelectionResult(
        agent_id="agent_x",
        agent_name="Agent X",
        short_name="AX",
        category="specialist",
        included=True,
        reason="test",
        conditions_evaluated=["test"],
        priority=10,
        data_sources=["SQL"],
    )
    engine._agent_started_at["agent_x"] = datetime.now(timezone.utc) - timedelta(milliseconds=20)

    payload = {
        "routes": [{"origin": "ORD", "destination": "LAX"}],
        "citations": [
            {
                "source_type": "SQL",
                "title": "SQL query: SELECT * FROM demo.ops_flights WHERE missing_connections > 0",
            }
        ],
    }

    await engine._emit_real_data_source_events_from_tool_payload("agent_x", payload)
    kinds = [etype for etype, _payload in captured]
    assert "data_source.query_complete" in kinds
    assert "data_source.query_failed" not in kinds


def test_readiness_data_source_checks_include_all_sources(monkeypatch):
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "")
    monkeypatch.setenv("AZURE_SEARCH_ADMIN_KEY", "")
    checks = backend_main._build_data_source_checks(postgres_ready=False)
    expected = {
        "SQL",
        "KQL",
        "GRAPH",
        "VECTOR_OPS",
        "VECTOR_REG",
        "VECTOR_AIRPORT",
        "NOSQL",
        "FABRIC_SQL",
    }
    assert set(checks.keys()) == expected
    assert checks["SQL"]["reachable"] is False
