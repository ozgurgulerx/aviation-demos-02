"""
Schema introspection for SQL, KQL, and Graph data sources.
Async-adapted from demos-01 schema_provider.py.
"""

from __future__ import annotations

import os
import json
import time
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default KQL schema for Fabric Eventhouse
DEFAULT_KQL_SCHEMA = {
    "tables": {
        "opensky_states": {
            "columns": {
                "time": "datetime", "icao24": "string", "callsign": "string",
                "origin_country": "string", "longitude": "real", "latitude": "real",
                "baro_altitude": "real", "velocity": "real", "true_track": "real",
                "vertical_rate": "real", "geo_altitude": "real", "squawk": "string",
                "on_ground": "bool", "category": "int",
            },
            "description": "ADS-B flight position data from OpenSky Network",
        },
        "hazards_airsigmets": {
            "columns": {
                "raw_text": "string", "hazard": "string", "severity": "string",
                "min_alt_ft_msl": "int", "max_alt_ft_msl": "int",
                "valid_time_from": "datetime", "valid_time_to": "datetime",
                "airsigmet_type": "string",
            },
            "description": "AIRMETs and SIGMETs weather hazards",
        },
        "hazards_gairmets": {
            "columns": {
                "raw_text": "string", "hazard": "string", "severity": "string",
                "valid_time_from": "datetime", "valid_time_to": "datetime",
            },
            "description": "G-AIRMETs weather hazards",
        },
    }
}

# Default SQL schema for ops tables
DEFAULT_SQL_SCHEMA = {
    "tables": {
        "ops_flight_legs": {
            "columns": {
                "leg_id": "text", "carrier_code": "text", "flight_no": "text",
                "tailnum": "text", "dep_station": "text", "arr_station": "text",
                "scheduled_dep_utc": "text", "scheduled_arr_utc": "text",
                "actual_dep_utc": "text", "actual_arr_utc": "text",
                "dep_delay_min": "text", "arr_delay_min": "text",
                "status": "text", "distance_nm": "text", "passengers": "text",
                "aircraft_type": "text",
            },
        },
        "ops_crew_rosters": {
            "columns": {
                "leg_id": "text", "crew_id": "text", "role": "text",
                "name": "text", "cumulative_duty_hours": "text",
                "duty_start_utc": "text", "duty_end_utc": "text",
                "rest_before_hours": "text", "legality_risk_flag": "text",
                "base_station": "text",
            },
        },
        "ops_mel_techlog_events": {
            "columns": {
                "leg_id": "text", "event_id": "text", "tailnum": "text",
                "jasc_code": "text", "jasc_title": "text",
                "deferred_flag": "text", "mel_category": "text",
                "reported_utc": "text", "description": "text",
            },
        },
        "ops_turnaround_milestones": {
            "columns": {
                "leg_id": "text", "milestone": "text",
                "planned_utc": "text", "actual_utc": "text",
                "delta_minutes": "text", "critical_path": "text",
            },
        },
        "ops_baggage_events": {
            "columns": {
                "leg_id": "text", "event_type": "text",
                "bag_count": "text", "pax_affected": "text",
                "event_utc": "text", "description": "text",
            },
        },
    }
}

# Default Graph schema
DEFAULT_GRAPH_SCHEMA = {
    "node_types": ["Airport", "Flight", "Aircraft", "Crew", "Gate"],
    "edge_types": ["DEPARTS_FROM", "ARRIVES_AT", "OPERATED_BY", "ASSIGNED_TO", "CONNECTS_TO"],
}


class AsyncSchemaProvider:
    """Provides schema snapshots for query writers (async-compatible)."""

    def __init__(self, pg_pool=None, cache_ttl: int = 300):
        self._pg_pool = pg_pool
        self._cache_ttl = cache_ttl
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts: float = 0.0

    async def snapshot(self) -> Dict[str, Any]:
        """Return cached or freshly-fetched schema snapshot."""
        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        sql_schema = DEFAULT_SQL_SCHEMA
        kql_schema = DEFAULT_KQL_SCHEMA
        graph_schema = DEFAULT_GRAPH_SCHEMA

        # Try loading KQL schema from env-provided JSON
        kql_json_path = os.getenv("FABRIC_KQL_SCHEMA_JSON", "")
        if kql_json_path and os.path.exists(kql_json_path):
            try:
                with open(kql_json_path) as f:
                    kql_schema = json.load(f)
            except Exception as e:
                logger.warning("Failed to load KQL schema from %s: %s", kql_json_path, e)

        # Try introspecting SQL schema from PostgreSQL
        if self._pg_pool:
            try:
                sql_schema = await self._introspect_sql_schema()
            except Exception as e:
                logger.warning("SQL schema introspection failed, using defaults: %s", e)

        self._cache = {
            "sql_schema": sql_schema,
            "kql_schema": kql_schema,
            "graph_schema": graph_schema,
        }
        self._cache_ts = now
        return self._cache

    async def _introspect_sql_schema(self) -> Dict[str, Any]:
        """Introspect PostgreSQL tables for ops schema."""
        visible_schemas = os.getenv("SQL_VISIBLE_SCHEMAS", "public,demo").split(",")
        schema_filter = ", ".join(f"'{s.strip()}'" for s in visible_schemas)

        query = f"""
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema IN ({schema_filter})
            ORDER BY table_schema, table_name, ordinal_position
        """
        async with self._pg_pool.acquire() as conn:
            rows = await conn.fetch(query)

        tables: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            table_key = f"{row['table_schema']}.{row['table_name']}" if row['table_schema'] != 'public' else row['table_name']
            if table_key not in tables:
                tables[table_key] = {"columns": {}}
            tables[table_key]["columns"][row["column_name"]] = row["data_type"]

        return {"tables": tables} if tables else DEFAULT_SQL_SCHEMA
