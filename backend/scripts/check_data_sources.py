#!/usr/bin/env python3
"""
Deterministic data-source probe for aviation multi-agent backend.

Outputs a JSON matrix with configured/reachable/sample query status per source.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import asyncpg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(ROOT / ".env")

from data_sources.unified_retriever import AsyncUnifiedRetriever  # noqa: E402


def _build_pg_dsn() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    host = os.getenv("PGHOST", "").strip()
    port = os.getenv("PGPORT", "5432").strip()
    database = os.getenv("PGDATABASE", "").strip()
    user = os.getenv("PGUSER", "").strip()
    password = os.getenv("PGPASSWORD", "").strip()
    if not host or not database or not user:
        return ""
    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{user}@{host}:{port}/{database}"


def _error_from_citations(citations: List[Any]) -> Tuple[str, str]:
    for citation in citations or []:
        if isinstance(citation, dict):
            title = str(citation.get("title") or "")
        else:
            title = str(getattr(citation, "title", "") or "")
        if not title:
            continue
        lowered = title.lower()
        is_error = (
            "error" in lowered
            or "failed" in lowered
            or "not configured" in lowered
            or "not installed" in lowered
            or "timed out" in lowered
            or "timeout" in lowered
            or "blocked" in lowered
            or "missing" in lowered
            or "no " in lowered
        )
        if not is_error:
            continue
        code = "SOURCE_QUERY_ERROR"
        if ":" in title:
            maybe_code = title.split(":", 1)[0].strip()
            if maybe_code and maybe_code.upper() == maybe_code and " " not in maybe_code:
                code = maybe_code
        elif "timeout" in lowered or "timed out" in lowered:
            code = "SOURCE_TIMEOUT"
        elif "not configured" in lowered or "missing" in lowered:
            code = "SOURCE_NOT_CONFIGURED"
        elif "not installed" in lowered:
            code = "SOURCE_DEPENDENCY_MISSING"
        return code, title
    return "", ""


async def _probe_source(retriever: AsyncUnifiedRetriever, source_type: str) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        if source_type == "SQL":
            rows, citations = await retriever.query_sql("flight delays at ORD in next 2 hours")
        elif source_type == "KQL":
            rows, citations = await retriever.query_kql("live aircraft positions near ORD")
        elif source_type == "GRAPH":
            rows, citations = await retriever.query_graph("connections from ORD", hops=2)
        elif source_type == "VECTOR_OPS":
            rows, citations = await retriever.query_semantic("weather disruption precedent", source="VECTOR_OPS")
        elif source_type == "VECTOR_REG":
            rows, citations = await retriever.query_semantic("FAR 117 duty limits", source="VECTOR_REG")
        elif source_type == "VECTOR_AIRPORT":
            rows, citations = await retriever.query_semantic("airport deicing procedures", source="VECTOR_AIRPORT")
        elif source_type == "NOSQL":
            rows, citations = await retriever.query_nosql("active NOTAMs for ORD")
        elif source_type == "FABRIC_SQL":
            rows, citations = await retriever.query_fabric_sql("historical delay patterns for ORD")
        else:
            return {
                "status": "error",
                "errorCode": "UNKNOWN_SOURCE",
                "errorMessage": f"Unsupported source type: {source_type}",
                "rowCount": 0,
                "latencyMs": int((time.perf_counter() - started) * 1000),
            }
    except Exception as exc:  # pragma: no cover
        return {
            "status": "error",
            "errorCode": "PROBE_EXCEPTION",
            "errorMessage": str(exc)[:220],
            "rowCount": 0,
            "latencyMs": int((time.perf_counter() - started) * 1000),
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    err_code, err_message = _error_from_citations(citations)
    if err_code:
        return {
            "status": "error",
            "errorCode": err_code,
            "errorMessage": err_message,
            "rowCount": len(rows),
            "latencyMs": latency_ms,
        }
    return {
        "status": "ok",
        "errorCode": "",
        "errorMessage": "",
        "rowCount": len(rows),
        "latencyMs": latency_ms,
    }


async def _run() -> Dict[str, Any]:
    pool = None
    retriever = None
    dsn = _build_pg_dsn()
    if dsn:
        try:
            pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=1)
        except Exception:
            pool = None

    try:
        retriever = AsyncUnifiedRetriever(pg_pool=pool)
        diagnostics = retriever.get_source_diagnostics()
        results: Dict[str, Any] = {}
        for source_type in diagnostics.keys():
            probe = await _probe_source(retriever, source_type)
            results[source_type] = {
                **diagnostics.get(source_type, {}),
                **probe,
            }
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "traceMode": os.getenv("DATA_SOURCE_TRACE_MODE", "actual"),
            "results": results,
        }
    finally:
        if retriever is not None:
            await retriever.close()
        if pool is not None:
            await pool.close()


def main() -> int:
    output = asyncio.run(_run())
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
