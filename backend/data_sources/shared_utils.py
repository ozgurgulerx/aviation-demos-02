"""
Shared utilities for data source layer.
Adapted from demos-01 shared_utils.py for async FastAPI context.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, FrozenSet, List, Tuple

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Azure OpenAI API version
# ---------------------------------------------------------------------------
OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")

# ---------------------------------------------------------------------------
# Citation dataclass — returned by every query method
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    source_type: str  # "SQL", "KQL", "GRAPH", "VECTOR_OPS", etc.
    identifier: str = ""
    title: str = ""
    content_preview: str = ""
    score: float = 0.0
    dataset: str = ""


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def env_csv(name: str, default: str) -> List[str]:
    raw = (os.getenv(name, default) or default).strip()
    if not raw:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for token in raw.split(","):
        value = token.strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(lowered)
    return out


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Model capability helpers
# ---------------------------------------------------------------------------

def supports_explicit_temperature(model_name: str) -> bool:
    """GPT-5/o-series deployments reject explicit temperature overrides."""
    model = (model_name or "").strip().lower()
    normalized = model.replace("-", "").replace("_", "")
    return not (
        model.startswith("gpt-5")
        or normalized.startswith("gpt5")
        or "gpt5" in normalized
        or model.startswith("o1")
        or model.startswith("o3")
        or model.startswith("o4")
        or normalized == "modelrouter"
    )


# ---------------------------------------------------------------------------
# Row preview helpers
# ---------------------------------------------------------------------------

def safe_preview_value(value: Any, max_chars: int = 180) -> Any:
    import json as _json

    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[: max_chars - 3] + "..."
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (dict, list, tuple)):
        try:
            serialized = _json.dumps(value, ensure_ascii=True)
        except Exception:
            serialized = str(value)
        return serialized if len(serialized) <= max_chars else serialized[: max_chars - 3] + "..."
    rendered = str(value)
    return rendered if len(rendered) <= max_chars else rendered[: max_chars - 3] + "..."


def build_rows_preview(
    rows: List[Dict[str, Any]],
    max_rows: int = 5,
    max_columns: int = 8,
    max_chars: int = 180,
) -> tuple[List[str], List[Dict[str, Any]], bool]:
    if not rows:
        return [], [], False

    hidden_keys = {"content_vector", "partial_schema", "fallback_sql"}
    columns: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            if not isinstance(key, str) or key.startswith("__") or key in hidden_keys:
                continue
            if key not in columns:
                columns.append(key)
                if len(columns) >= max_columns:
                    break
        if len(columns) >= max_columns:
            break

    preview: List[Dict[str, Any]] = []
    for row in rows[:max_rows]:
        if not isinstance(row, dict):
            continue
        item: Dict[str, Any] = {}
        for column in columns:
            if column in row:
                item[column] = safe_preview_value(row[column], max_chars=max_chars)
        if item:
            preview.append(item)

    return columns, preview, len(rows) > len(preview)


# ---------------------------------------------------------------------------
# Word-boundary-aware keyword matching
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _compile_keyword_pattern(keywords: FrozenSet[str]) -> re.Pattern:
    escaped = sorted((re.escape(k) for k in keywords if k), key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)", re.IGNORECASE)


def matches_any(text: str, keywords: FrozenSet[str]) -> bool:
    if not text or not keywords:
        return False
    return bool(_compile_keyword_pattern(keywords).search(text))


# ---------------------------------------------------------------------------
# Centralized keyword sets for query classification
# ---------------------------------------------------------------------------

OPS_TABLE_SIGNALS: FrozenSet[str] = frozenset({
    "mel", "techlog", "tech log", "technical log", "minimum equipment",
    "dispatch", "dispatched", "dispatchable", "deferred", "jasc",
    "crew", "duty", "fatigue", "legality",
    "baggage", "mishandled", "luggage",
    "turnaround", "milestones", "milestone", "ground handling",
    "flight leg", "flight legs", "leg_id",
    "ops_flight_legs", "ops_turnaround_milestones", "ops_crew_rosters",
    "ops_mel_techlog_events", "ops_baggage_events",
    "tail", "tailnum", "inbound", "downstream",
    "dependency", "dependencies", "chain", "trace",
    "propagate", "propagation",
})

FABRIC_SQL_DELAY_TRIGGERS: FrozenSet[str] = frozenset({
    "delay", "delays", "delayed",
    "on-time", "on time", "cancellation", "cancellations",
    "schedule performance",
    "bts", "carrier performance", "carrier delay", "weather delay",
    "nas delay", "delay cause", "average delay",
    "cancellation rate", "on time performance",
})


# ---------------------------------------------------------------------------
# Airport / ICAO constants
# ---------------------------------------------------------------------------

ENGLISH_4LETTER_BLOCKLIST: set[str] = {
    "WHAT", "WITH", "FROM", "YOUR", "SHOW", "THIS", "THAT", "WHEN",
    "WILL", "HAVE", "DOES", "BEEN", "WERE", "THEY", "THEM", "THEN",
    "THAN", "EACH", "MADE", "FIND", "HERE", "MANY", "SOME", "LIKE",
    "LONG", "MAKE", "JUST", "OVER", "SUCH", "TAKE", "YEAR", "ALSO",
    "INTO", "MOST", "ONLY", "COME", "VERY", "WELL", "BACK", "MUCH",
    "GIVE", "EVEN", "WANT", "GOOD", "LOOK", "LAST", "TELL", "NEED",
    "NEAR", "AREA", "BOTH", "KEEP", "HELP", "LINE", "TURN", "MOVE",
    "LIVE", "REAL", "LEFT", "SAME", "ABLE", "OPEN", "SEEM", "SURE",
    "HIGH", "RISK", "EVER", "NEXT", "TYPE", "LIST", "DATA", "USED",
    "BEST", "DONE", "FULL", "MUST", "KNOW", "TIME", "WENT", "GATE",
    "TAXI", "LAND", "HOLD", "TAKE", "CALL", "NOTE",
    "TAIL", "LEGS", "WING", "CREW", "FUEL", "NOSE", "RAMP", "GEAR",
    "LOAD", "PLAN", "PART", "LOSS", "MILE", "PATH", "RATE", "BASE",
    "CODE", "ZONE", "WIND", "LATE", "FLOW", "STOP", "WAIT", "DOWN",
    "SIZE", "TECH", "BIRD", "DECK", "DROP", "FAIL", "FLAG", "FORM",
    "LOCK", "LOOP", "PACK", "PORT", "PUSH", "SLOT", "SPAN", "STEP",
    "TANK", "TEST", "TIRE", "TRIM", "WASH", "DAYS", "FAST", "HALF",
    "KIND", "LESS", "MORE", "NAME", "ONCE", "PAST", "SAID", "SIDE",
    "TOLD", "WORD", "ZERO",
}

CITY_AIRPORT_MAP: Dict[str, List[str]] = {
    "new york": ["KJFK", "KLGA", "KEWR"],
    "nyc": ["KJFK", "KLGA", "KEWR"],
    "istanbul": ["LTFM", "LTBA", "LTFJ"],
    "london": ["EGLL", "EGKK", "EGSS"],
    "chicago": ["KORD", "KMDW"],
    "dallas": ["KDFW", "KDAL"],
    "los angeles": ["KLAX"],
    "san francisco": ["KSFO"],
    "denver": ["KDEN"],
    "atlanta": ["KATL"],
    "detroit": ["KDTW"],
    "miami": ["KMIA", "KFLL"],
}

IATA_TO_ICAO_MAP: Dict[str, str] = {
    "JFK": "KJFK", "LGA": "KLGA", "EWR": "KEWR",
    "ATL": "KATL", "ORD": "KORD", "LAX": "KLAX",
    "DFW": "KDFW", "DEN": "KDEN", "SFO": "KSFO",
    "DTW": "KDTW", "MIA": "KMIA", "FLL": "KFLL",
    "IAH": "KIAH", "MSP": "KMSP", "SEA": "KSEA",
    "BOS": "KBOS", "PHX": "KPHX", "CLT": "KCLT",
    "IST": "LTFM", "SAW": "LTFJ", "ESB": "LTAC",
    "AYT": "LTAI", "ADB": "LTBJ",
    "LHR": "EGLL", "LGW": "EGKK",
    "CDG": "LFPG", "FRA": "EDDF", "AMS": "EHAM",
}


# ---------------------------------------------------------------------------
# Tool name canonicalization
# ---------------------------------------------------------------------------

KNOWN_TOOLS: set[str] = {
    "KQL", "SQL", "GRAPH", "VECTOR_REG", "VECTOR_OPS",
    "VECTOR_AIRPORT", "NOSQL", "FABRIC_SQL",
}

TOOL_ALIASES: Dict[str, str] = {
    "EVENTHOUSEKQL": "KQL", "KQL": "KQL",
    "WAREHOUSESQL": "SQL", "SQL": "SQL",
    "FABRICGRAPH": "GRAPH", "GRAPHTRAVERSAL": "GRAPH", "GRAPH": "GRAPH",
    "FOUNDRYIQ": "VECTOR_REG", "AZUREAISEARCH": "VECTOR_REG",
    "VECTOR_REG": "VECTOR_REG", "VECTOR_OPS": "VECTOR_OPS",
    "VECTOR_AIRPORT": "VECTOR_AIRPORT",
    "NOSQL": "NOSQL",
    "FABRIC_SQL": "FABRIC_SQL", "FABRICSQL": "FABRIC_SQL",
    "FABRICWAREHOUSESQL": "FABRIC_SQL",
    "LAKEHOUSEDELTA": "KQL",
}


def canon_tool(raw: str) -> str:
    value = (raw or "").strip().upper()
    mapped = TOOL_ALIASES.get(value, value)
    return mapped if mapped in KNOWN_TOOLS else ""
