"""
Async LLM-based query writers (Text2SQL / Text2KQL).
Adapted from demos-01 query_writers.py — uses AsyncAzureOpenAI.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from data_sources.azure_client import get_shared_async_client
from data_sources.shared_utils import OPENAI_API_VERSION, supports_explicit_temperature


def _strip_fences(text: str) -> str:
    out = re.sub(r"^```(?:sql|kql|json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    out = re.sub(r"\s*```$", "", out)
    return out.strip()


class AsyncSQLWriter:
    """Async LLM-based Text-to-SQL writer."""

    def __init__(self, model: Optional[str] = None):
        self.model = (
            model
            or os.getenv("AZURE_OPENAI_WORKER_DEPLOYMENT_NAME")
            or os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")
        )

    async def generate(
        self,
        user_query: str,
        evidence_type: str,
        sql_schema: Dict[str, Any],
        entities: Dict[str, Any],
        time_window: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
    ) -> str:
        client, _ = await get_shared_async_client(api_version=OPENAI_API_VERSION)

        prompt = """You are SQL_WRITER. Output SQL ONLY.

Rules:
- Use only tables/columns provided in sql_schema.
- If hint_tables is provided in constraints, PREFER those tables for the query.
- Prefer simple SELECTs with WHERE filters and LIMIT.
- If a requested column is not present in sql_schema, do not guess.
- If needed columns are missing, output exactly:
-- NEED_SCHEMA: <what is missing>
- Never generate INSERT/UPDATE/DELETE/DDL.
- IMPORTANT: Airport codes, flight IDs, and other identifiers MUST come ONLY from the entities object.
- If entities.airports AND entities.flight_ids are both empty, write a general aggregate query.
- Many ops_* tables store ALL columns as TEXT. Cast appropriately:
  * Cast timestamp columns via column::timestamptz
  * Cast numeric columns via column::numeric or column::integer
- ops_flight_legs contains carrier_code, flight_no, tailnum, distance_nm directly.
- Alias conventions: l = ops_flight_legs, m = ops_turnaround_milestones, c = ops_crew_rosters, t = ops_mel_techlog_events, b = ops_baggage_events.
"""
        payload = {
            "user_query": user_query,
            "evidence_type": evidence_type,
            "sql_schema": sql_schema,
            "entities": entities,
            "time_window": time_window,
            "constraints": constraints or {},
        }
        request_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        }
        if supports_explicit_temperature(self.model):
            request_kwargs["temperature"] = 0

        response = await client.chat.completions.create(**request_kwargs)
        return _strip_fences(response.choices[0].message.content or "")


class AsyncKQLWriter:
    """Async LLM-based Text-to-KQL writer."""

    def __init__(self, model: Optional[str] = None):
        self.model = (
            model
            or os.getenv("AZURE_OPENAI_WORKER_DEPLOYMENT_NAME")
            or os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")
        )

    async def generate(
        self,
        user_query: str,
        evidence_type: str,
        kql_schema: Dict[str, Any],
        entities: Dict[str, Any],
        time_window: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
    ) -> str:
        client, _ = await get_shared_async_client(api_version=OPENAI_API_VERSION)

        prompt = """You are KQL_WRITER. Output KQL ONLY.

Rules:
- Use only tables/columns provided in kql_schema.
- Always include a time filter using the horizon.
- Start with a valid table reference (or let-binding followed by a table).
- Do not emit semicolons except required let-binding terminators.
- Do not use unsupported functions (for example: time_now()).
- If needed columns are missing, output exactly:
// NEED_SCHEMA: <what is missing>
- Never invent table names.
- IMPORTANT: Airport codes, flight IDs, and other identifiers MUST come ONLY from the entities object.
"""
        payload = {
            "user_query": user_query,
            "evidence_type": evidence_type,
            "kql_schema": kql_schema,
            "entities": entities,
            "time_window": time_window,
            "constraints": constraints or {},
        }
        request_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        }
        if supports_explicit_temperature(self.model):
            request_kwargs["temperature"] = 0

        response = await client.chat.completions.create(**request_kwargs)
        return _strip_fences(response.choices[0].message.content or "")
