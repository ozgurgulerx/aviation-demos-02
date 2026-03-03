"""
Aviation agent tools — module exports for retriever wiring.
"""

import asyncio
import json
import re
import time
from typing import Any, Coroutine, Dict, List, Sequence, Tuple
import structlog

from data_sources.shared_utils import Citation

_rq_logger = structlog.get_logger()


def _infer_source_type_from_coro(coro: Coroutine[Any, Any, Any]) -> str:
    code = getattr(coro, "cr_code", None)
    frame = getattr(coro, "cr_frame", None)
    name = getattr(code, "co_name", "")
    if name == "query_sql":
        return "SQL"
    if name == "query_kql":
        return "KQL"
    if name == "query_graph":
        return "GRAPH"
    if name == "query_nosql":
        return "NOSQL"
    if name == "query_fabric_sql":
        return "FABRIC_SQL"
    if name == "query_semantic":
        source = getattr(frame, "f_locals", {}).get("source")
        if isinstance(source, str) and source.strip():
            return source.strip()
        return "VECTOR_OPS"
    return "UNKNOWN"


def _extract_error_code(message: str, default: str) -> str:
    if not message:
        return default
    # Explicit code prefix format: CODE: message
    explicit = re.match(r"^\s*([A-Z0-9_]{3,})\s*:\s*", message)
    if explicit:
        return explicit.group(1)
    lowered = message.lower()
    if "timed out" in lowered or "timeout" in lowered:
        return "SOURCE_TIMEOUT"
    if "not configured" in lowered or "missing" in lowered:
        return "SOURCE_NOT_CONFIGURED"
    if "not installed" in lowered:
        return "SOURCE_DEPENDENCY_MISSING"
    if "no fabric token" in lowered or "token" in lowered:
        return "SOURCE_AUTH_ERROR"
    if "schema insufficient" in lowered or "need_schema" in lowered:
        return "SOURCE_SCHEMA_INSUFFICIENT"
    if "no database connection" in lowered:
        return "SOURCE_UNAVAILABLE"
    if "error" in lowered or "failed" in lowered:
        return "SOURCE_QUERY_ERROR"
    return default


def _is_explicit_error_title(title: str) -> bool:
    if not title:
        return False
    if re.match(r"^\s*([A-Z0-9_]{3,})\s*:\s*", title):
        return True
    lowered = title.strip().lower()
    error_prefixes = (
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
    if any(lowered.startswith(prefix) for prefix in error_prefixes):
        return True
    known_error_titles = {
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
    return lowered in known_error_titles


def _citation_to_dict(citation: Any) -> Dict[str, Any]:
    if citation is None:
        return {}
    if isinstance(citation, dict):
        return citation
    if hasattr(citation, "__dict__"):
        return dict(citation.__dict__)
    return {}


def _build_error_citation(
    source_type: str,
    code: str,
    message: str,
    retryable: bool,
) -> Citation:
    return Citation(
        source_type=source_type or "UNKNOWN",
        title=f"{code}: {message}",
        content_preview=json.dumps(
            {"code": code, "retryable": retryable, "sourceType": source_type or "UNKNOWN"},
            ensure_ascii=True,
        ),
        score=0.0,
        dataset="retriever_wrapper",
    )


def source_errors_from_citations(citations: Sequence[Any]) -> List[Dict[str, Any]]:
    """Extract source errors from citation payloads for tool-level sourceErrors field."""
    errors: List[Dict[str, Any]] = []
    for citation in citations or []:
        c = _citation_to_dict(citation)
        source_type = str(c.get("source_type") or c.get("sourceType") or c.get("source") or "UNKNOWN")
        title = str(c.get("title") or "")
        preview = c.get("content_preview") or c.get("contentPreview")
        preview_error_code = ""
        retryable_from_preview = False
        if isinstance(preview, str) and preview.strip():
            try:
                parsed_preview = json.loads(preview)
            except Exception:
                parsed_preview = None
            if isinstance(parsed_preview, dict):
                preview_error_code = str(parsed_preview.get("code") or "").strip()
                retryable_from_preview = bool(parsed_preview.get("retryable"))

        is_error = bool(preview_error_code) or _is_explicit_error_title(title)
        if not is_error:
            continue
        code = preview_error_code or _extract_error_code(title, "SOURCE_QUERY_ERROR")
        retryable = (
            retryable_from_preview
            if preview_error_code
            else code in {"SOURCE_TIMEOUT", "SOURCE_UNAVAILABLE", "SOURCE_NOT_CONFIGURED"}
        )
        errors.append(
            {
                "sourceType": source_type,
                "errorCode": code,
                "message": title[:220],
                "retryable": retryable,
            }
        )
    # dedupe identical entries while preserving order
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for err in errors:
        key = (err["sourceType"], err["errorCode"], err["message"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(err)
    return deduped


def attach_source_errors(payload: Dict[str, Any], citations: Sequence[Any]) -> Dict[str, Any]:
    """Attach sourceErrors to a tool payload when citation-level failures exist."""
    errors = source_errors_from_citations(citations)
    if errors:
        payload["sourceErrors"] = errors
    return payload


async def retriever_query(
    coro: Coroutine[Any, Any, Tuple[List, List]], timeout: int = 50
) -> Tuple[List, List]:
    """Wrap a retriever coroutine with a hard timeout. Returns explicit error citations on failure."""
    source_type = _infer_source_type_from_coro(coro)
    started = time.perf_counter()
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError) as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _rq_logger.warning(
            "retriever_query_timeout",
            error=str(e),
            timeout=timeout,
            source_type=source_type,
            elapsed_ms=elapsed_ms,
        )
        return [], [
            _build_error_citation(
                source_type=source_type,
                code="SOURCE_TIMEOUT",
                message=f"Query timed out after {timeout}s",
                retryable=True,
            )
        ]
    except Exception as e:
        _rq_logger.warning("retriever_query_error", error=str(e), source_type=source_type)
        return [], [
            _build_error_citation(
                source_type=source_type,
                code=_extract_error_code(str(e), "SOURCE_QUERY_ERROR"),
                message=f"Retriever query failed: {str(e)[:180]}",
                retryable=False,
            )
        ]


async def retriever_query_multi(
    coro: Coroutine[Any, Any, Dict[str, Tuple[List, List]]], timeout: int = 60
) -> Dict[str, Tuple[List, List]]:
    """Wrap query_multiple with timeout and preserve explicit per-source error citations."""
    frame = getattr(coro, "cr_frame", None)
    requested_sources = getattr(frame, "f_locals", {}).get("sources")
    source_list = [s for s in (requested_sources or []) if isinstance(s, str)]
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError) as e:
        _rq_logger.warning("retriever_query_multi_timeout", error=str(e), timeout=timeout)
        return {
            source: (
                [],
                [
                    _build_error_citation(
                        source_type=source,
                        code="SOURCE_TIMEOUT",
                        message=f"query_multiple timed out after {timeout}s",
                        retryable=True,
                    )
                ],
            )
            for source in source_list
        }
    except Exception as e:
        _rq_logger.warning("retriever_query_multi_error", error=str(e))
        code = _extract_error_code(str(e), "SOURCE_QUERY_ERROR")
        return {
            source: (
                [],
                [
                    _build_error_citation(
                        source_type=source,
                        code=code,
                        message=f"query_multiple failed: {str(e)[:180]}",
                        retryable=False,
                    )
                ],
            )
            for source in source_list
        }


from agents.tools import (
    crew_tools,
    diversion_tools,
    fatigue_tools,
    fleet_tools,
    flight_tools,
    maintenance_tools,
    monitor_tools,
    network_tools,
    operations_tools,
    passenger_tools,
    regulatory_tools,
    route_tools,
    safety_tools,
    situation_tools,
    weather_safety_tools,
)

# All modules that support set_retriever()
RETRIEVER_MODULES = [
    crew_tools,
    diversion_tools,
    fatigue_tools,
    fleet_tools,
    flight_tools,
    maintenance_tools,
    monitor_tools,
    network_tools,
    operations_tools,
    passenger_tools,
    regulatory_tools,
    route_tools,
    safety_tools,
    situation_tools,
    weather_safety_tools,
]
