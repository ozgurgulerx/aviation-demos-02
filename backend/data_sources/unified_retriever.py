"""
Async Unified Retriever — central interface to all 8 data sources.
Adapted from demos-01 UnifiedRetriever (sync Flask) to async FastAPI.

Data Sources:
1. SQL (PostgreSQL) — ops_flight_legs, ops_crew_rosters, ops_mel_techlog_events, etc.
2. KQL (Fabric Eventhouse) — opensky_states, hazards_airsigmets, etc.
3. GRAPH (Fabric Graph / PostgreSQL fallback) — airport/flight connectivity
4. VECTOR_OPS (Azure AI Search) — ASRS safety narratives
5. VECTOR_REG (Azure AI Search) — FAA/EASA regulatory docs
6. VECTOR_AIRPORT (Azure AI Search) — Airport ops documents
7. NOSQL (Cosmos DB) — NOTAMs
8. FABRIC_SQL (Fabric SQL Warehouse) — BTS on-time performance
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from data_sources.shared_utils import (
    Citation,
    IATA_TO_ICAO_MAP,
    ENGLISH_4LETTER_BLOCKLIST,
    CITY_AIRPORT_MAP,
    OPENAI_API_VERSION,
    build_rows_preview,
    env_bool,
    env_int,
)
from data_sources.schema_provider import AsyncSchemaProvider
from data_sources.query_writers import AsyncSQLWriter, AsyncKQLWriter

logger = logging.getLogger(__name__)

# Sentinel for optional imports
_HAS_SEARCH = False
_HAS_COSMOS = False

try:
    from azure.search.documents.aio import SearchClient
    from azure.search.documents.models import VectorizedQuery
    from azure.core.credentials import AzureKeyCredential
    _HAS_SEARCH = True
except ImportError:
    logger.info("azure-search-documents not installed, vector search disabled")

try:
    from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
    _HAS_COSMOS = True
except ImportError:
    logger.info("azure-cosmos not installed, Cosmos DB disabled")


def _extract_airports_from_query(query: str) -> List[str]:
    """Extract IATA/ICAO airport codes from query text."""
    codes: List[str] = []
    # Check IATA codes (3-letter)
    for match in re.finditer(r'\b([A-Z]{3})\b', query.upper()):
        code = match.group(1)
        if code in IATA_TO_ICAO_MAP:
            icao = IATA_TO_ICAO_MAP[code]
            if icao not in codes:
                codes.append(icao)
            if code not in codes:
                codes.append(code)
    # Check ICAO codes (4-letter starting with K/L/E)
    for match in re.finditer(r'\b(K[A-Z]{3}|LT[A-Z]{2}|EG[A-Z]{2}|LF[A-Z]{2}|ED[A-Z]{2}|EH[A-Z]{2})\b', query.upper()):
        code = match.group(1)
        if code not in ENGLISH_4LETTER_BLOCKLIST and code not in codes:
            codes.append(code)
    # Check city names
    lower = query.lower()
    for city, airport_codes in CITY_AIRPORT_MAP.items():
        if city in lower:
            for ac in airport_codes:
                if ac not in codes:
                    codes.append(ac)
    return codes


class AsyncUnifiedRetriever:
    """
    Async unified retrieval interface for all 8 aviation data sources.
    Each query method returns (rows, citations) for consistent consumption by agent tools.
    """

    def __init__(self, pg_pool=None):
        self._pg_pool = pg_pool
        self._http: Optional[httpx.AsyncClient] = None
        self._schema_provider = AsyncSchemaProvider(pg_pool=pg_pool)
        self._sql_writer = AsyncSQLWriter()
        self._kql_writer = AsyncKQLWriter()

        # Search clients (lazy-init)
        self._search_clients: Dict[str, Any] = {}

        # Cosmos client + container (lazy-init)
        self._cosmos_client: Any = None
        self._cosmos_credential: Any = None
        self._cosmos_container: Any = None

        # Embedding cache
        self._embedding_cache: Dict[str, List[float]] = {}

        # Config
        self._fabric_kql_endpoint = os.getenv("FABRIC_KQL_ENDPOINT", "")
        self._fabric_kql_database = os.getenv("FABRIC_KQL_DATABASE", "")
        self._fabric_graph_endpoint = os.getenv("FABRIC_GRAPH_ENDPOINT", "")
        self._fabric_sql_endpoint = os.getenv("FABRIC_SQL_ENDPOINT", "")
        self._embedding_deployment = os.getenv("AZURE_TEXT_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small")

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        for key, client in self._search_clients.items():
            try:
                await client.close()
            except Exception as e:
                logger.warning("Failed to close search client %s: %s", key, e)
        self._search_clients.clear()
        if self._cosmos_client:
            try:
                await self._cosmos_client.close()
            except Exception as e:
                logger.warning("Failed to close Cosmos client: %s", e)
            self._cosmos_client = None
            self._cosmos_container = None
        if self._cosmos_credential:
            try:
                await self._cosmos_credential.close()
            except Exception as e:
                logger.warning("Failed to close Cosmos credential: %s", e)
            self._cosmos_credential = None

    # ------------------------------------------------------------------
    # Fabric token acquisition
    # ------------------------------------------------------------------
    async def _get_fabric_token(self) -> str:
        """Get Fabric/Azure token for REST API calls."""
        static_token = os.getenv("FABRIC_BEARER_TOKEN", "").strip()
        if static_token and env_bool("ALLOW_STATIC_FABRIC_BEARER", False):
            return static_token

        # Use service principal if configured
        client_id = os.getenv("FABRIC_CLIENT_ID", "")
        client_secret = os.getenv("FABRIC_CLIENT_SECRET", "")
        tenant_id = os.getenv("FABRIC_TENANT_ID", "")

        if client_id and client_secret and tenant_id:
            http = await self._get_http()
            resp = await http.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://analysis.windows.net/powerbi/api/.default",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

        # Fallback to Azure CLI credential
        try:
            from azure.identity.aio import AzureCliCredential
            cred = AzureCliCredential()
            token = await cred.get_token("https://analysis.windows.net/powerbi/api/.default")
            await cred.close()
            return token.token
        except Exception as e:
            logger.warning("Fabric token acquisition failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # 1. SQL (PostgreSQL via asyncpg)
    # ------------------------------------------------------------------
    async def query_sql(
        self,
        query: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Execute a natural language query against PostgreSQL ops tables."""
        if not self._pg_pool:
            return [], [Citation(source_type="SQL", title="No database connection")]

        try:
            schemas = schema or (await self._schema_provider.snapshot()).get("sql_schema", {})
            airports = _extract_airports_from_query(query)

            sql = await self._sql_writer.generate(
                user_query=query,
                evidence_type="FlightSchedule",
                sql_schema=schemas,
                entities={"airports": airports, "flight_ids": [], "routes": []},
                time_window={"horizon_min": 60},
            )

            if not sql or "NEED_SCHEMA" in sql:
                return [], [Citation(source_type="SQL", title="Schema insufficient for query")]

            # Safety check — only SELECT
            sql_upper = sql.strip().upper()
            if not sql_upper.startswith("SELECT"):
                logger.warning("Blocked non-SELECT SQL: %s", sql[:100])
                return [], [Citation(source_type="SQL", title="Only SELECT queries allowed")]

            async with self._pg_pool.acquire() as conn:
                records = await conn.fetch(sql)

            rows = [dict(r) for r in records]
            citations = [
                Citation(
                    source_type="SQL",
                    identifier=f"sql-{hash(sql) % 10000}",
                    title=f"SQL query: {sql[:80]}",
                    content_preview=str(rows[:2]) if rows else "No results",
                    score=1.0,
                    dataset="postgresql",
                )
            ]
            return rows, citations

        except Exception as e:
            logger.error("SQL query failed: %s", e)
            return [], [Citation(source_type="SQL", title=f"SQL error: {str(e)[:100]}")]

    # ------------------------------------------------------------------
    # 2. KQL (Fabric Eventhouse via REST)
    # ------------------------------------------------------------------
    async def query_kql(
        self,
        query: str,
        window_minutes: int = 60,
    ) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Execute a natural language query against Fabric Eventhouse (Kusto)."""
        if not self._fabric_kql_endpoint:
            return [], [Citation(source_type="KQL", title="KQL endpoint not configured")]

        try:
            schemas = (await self._schema_provider.snapshot()).get("kql_schema", {})
            airports = _extract_airports_from_query(query)

            kql = await self._kql_writer.generate(
                user_query=query,
                evidence_type="LivePositions",
                kql_schema=schemas,
                entities={"airports": airports, "flight_ids": []},
                time_window={"horizon_min": window_minutes},
            )

            if not kql or "NEED_SCHEMA" in kql:
                return [], [Citation(source_type="KQL", title="KQL schema insufficient")]

            token = await self._get_fabric_token()
            if not token:
                return [], [Citation(source_type="KQL", title="No Fabric token available")]

            http = await self._get_http()
            resp = await http.post(
                self._fabric_kql_endpoint,
                json={"db": self._fabric_kql_database, "csl": kql},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            rows = self._parse_kusto_response(data)
            citations = [
                Citation(
                    source_type="KQL",
                    identifier=f"kql-{hash(kql) % 10000}",
                    title=f"KQL query: {kql[:80]}",
                    content_preview=str(rows[:2]) if rows else "No results",
                    score=1.0,
                    dataset="eventhouse",
                )
            ]
            return rows, citations

        except Exception as e:
            logger.error("KQL query failed: %s", e)
            return [], [Citation(source_type="KQL", title=f"KQL error: {str(e)[:100]}")]

    def _parse_kusto_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Kusto REST API response into list of dicts."""
        rows: List[Dict[str, Any]] = []
        try:
            frames = data.get("Tables") or data.get("tables") or []
            if not frames:
                frames = [data] if "Columns" in data or "columns" in data else []

            for frame in frames:
                columns = frame.get("Columns") or frame.get("columns") or []
                col_names = [c.get("ColumnName") or c.get("columnName") or f"col_{i}" for i, c in enumerate(columns)]
                raw_rows = frame.get("Rows") or frame.get("rows") or []
                for raw_row in raw_rows:
                    if isinstance(raw_row, list):
                        rows.append(dict(zip(col_names, raw_row)))
                    elif isinstance(raw_row, dict):
                        rows.append(raw_row)
                if rows:
                    break
        except Exception as e:
            logger.warning("Kusto response parse error: %s", e)
        return rows

    # ------------------------------------------------------------------
    # 3. GRAPH (Fabric Graph / PostgreSQL fallback)
    # ------------------------------------------------------------------
    async def query_graph(
        self,
        query: str,
        hops: int = 2,
    ) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Query the aviation knowledge graph."""
        if self._fabric_graph_endpoint:
            try:
                return await self._query_graph_fabric(query, hops)
            except Exception as e:
                logger.warning("Fabric Graph failed, trying PG fallback: %s", e)

        # PostgreSQL BFS fallback
        if self._pg_pool:
            return await self._query_graph_pg_fallback(query, hops)

        return [], [Citation(source_type="GRAPH", title="No graph endpoint configured")]

    async def _query_graph_fabric(self, query: str, hops: int) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        token = await self._get_fabric_token()
        http = await self._get_http()

        airports = _extract_airports_from_query(query)
        start_node = airports[0] if airports else "KORD"

        resp = await http.post(
            self._fabric_graph_endpoint,
            json={"startNode": start_node, "hops": hops, "query": query},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        rows = [{"type": "node", **n} for n in nodes] + [{"type": "edge", **e} for e in edges]

        citations = [
            Citation(
                source_type="GRAPH",
                identifier=f"graph-{start_node}",
                title=f"Graph traversal from {start_node} ({hops} hops)",
                content_preview=f"{len(nodes)} nodes, {len(edges)} edges",
                score=1.0,
                dataset="fabric_graph",
            )
        ]
        return rows, citations

    async def _query_graph_pg_fallback(self, query: str, hops: int) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """BFS graph traversal using ops_graph_edges in PostgreSQL."""
        airports = _extract_airports_from_query(query)
        start = airports[0] if airports else "KORD"

        sql = """
            WITH RECURSIVE graph_walk AS (
                SELECT source_id, target_id, edge_type, 1 AS depth
                FROM ops_graph_edges
                WHERE source_id = $1
                UNION ALL
                SELECT e.source_id, e.target_id, e.edge_type, gw.depth + 1
                FROM ops_graph_edges e
                JOIN graph_walk gw ON e.source_id = gw.target_id
                WHERE gw.depth < $2
            )
            SELECT DISTINCT source_id, target_id, edge_type, depth
            FROM graph_walk
            ORDER BY depth
            LIMIT 100
        """
        try:
            async with self._pg_pool.acquire() as conn:
                records = await conn.fetch(sql, start, hops)
            rows = [dict(r) for r in records]
            citations = [
                Citation(
                    source_type="GRAPH",
                    identifier=f"graph-pg-{start}",
                    title=f"PG graph BFS from {start} ({hops} hops)",
                    content_preview=f"{len(rows)} edges found",
                    score=0.8,
                    dataset="postgresql_graph",
                )
            ]
            return rows, citations
        except Exception as e:
            logger.error("Graph PG fallback failed: %s", e)
            return [], [Citation(source_type="GRAPH", title=f"Graph error: {str(e)[:100]}")]

    # ------------------------------------------------------------------
    # 4-6. Semantic Search (Azure AI Search — 3 indexes)
    # ------------------------------------------------------------------
    async def query_semantic(
        self,
        query: str,
        top: int = 5,
        source: str = "VECTOR_OPS",
    ) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Search Azure AI Search index (vector + BM25 hybrid)."""
        if not _HAS_SEARCH:
            return [], [Citation(source_type=source, title="azure-search-documents not installed")]

        index_map = {
            "VECTOR_OPS": os.getenv("AZURE_SEARCH_INDEX_OPS_NAME", "idx_ops_narratives"),
            "VECTOR_REG": os.getenv("AZURE_SEARCH_INDEX_REGULATORY_NAME", "idx_regulatory"),
            "VECTOR_AIRPORT": os.getenv("AZURE_SEARCH_INDEX_AIRPORT_NAME", "idx_airport_ops_docs"),
        }
        index_name = index_map.get(source)
        if not index_name:
            return [], [Citation(source_type=source, title=f"Unknown search source: {source}")]

        search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
        search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY", "")
        if not search_endpoint or not search_key:
            return [], [Citation(source_type=source, title="Search endpoint/key not configured")]

        try:
            client = await self._get_search_client(search_endpoint, search_key, index_name)
            embedding = await self.get_embedding(query)

            vector_query = VectorizedQuery(
                vector=embedding,
                k_nearest_neighbors=top,
                fields="content_vector",
            ) if embedding else None

            results = await client.search(
                search_text=query,
                vector_queries=[vector_query] if vector_query else None,
                top=top,
            )

            rows: List[Dict[str, Any]] = []
            citations: List[Citation] = []
            async for result in results:
                row = {k: v for k, v in result.items() if k != "content_vector"}
                rows.append(row)
                citations.append(Citation(
                    source_type=source,
                    identifier=str(result.get("id", "")),
                    title=str(result.get("title", result.get("chunk_id", "")))[:100],
                    content_preview=str(result.get("content", result.get("chunk", "")))[:200],
                    score=result.get("@search.score", 0.0),
                    dataset=index_name,
                ))

            return rows, citations

        except Exception as e:
            logger.error("Semantic search failed (%s): %s", source, e)
            return [], [Citation(source_type=source, title=f"Search error: {str(e)[:100]}")]

    async def _get_search_client(self, endpoint: str, key: str, index_name: str):
        cache_key = f"{endpoint}/{index_name}"
        if cache_key not in self._search_clients:
            self._search_clients[cache_key] = SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(key),
            )
        return self._search_clients[cache_key]

    # ------------------------------------------------------------------
    # 7. NOSQL (Cosmos DB — NOTAMs)
    # ------------------------------------------------------------------
    async def query_nosql(
        self,
        query: str,
    ) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Query Cosmos DB for NOTAMs."""
        if not _HAS_COSMOS:
            return [], [Citation(source_type="NOSQL", title="azure-cosmos not installed")]

        cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT", "")
        cosmos_key = os.getenv("AZURE_COSMOS_KEY", "")
        cosmos_db_name = os.getenv("AZURE_COSMOS_DATABASE", "aviationrag")
        cosmos_container_name = os.getenv("AZURE_COSMOS_CONTAINER", "notams")

        if not cosmos_endpoint:
            return [], [Citation(source_type="NOSQL", title="Cosmos endpoint not configured")]

        try:
            container = await self._get_cosmos_container(
                cosmos_endpoint, cosmos_key, cosmos_db_name, cosmos_container_name,
            )

            airports = _extract_airports_from_query(query)
            if airports:
                # Use parameterized query to prevent injection
                sanitized = [re.sub(r'[^A-Z0-9]', '', a.upper())[:6] for a in airports[:5]]
                params: List[Dict[str, str]] = []
                conditions = []
                for i, code in enumerate(sanitized):
                    param_name = f"@airport{i}"
                    conditions.append(f"CONTAINS(c.location, {param_name})")
                    params.append({"name": param_name, "value": code})
                cosmos_query = f"SELECT * FROM c WHERE ({' OR '.join(conditions)}) OFFSET 0 LIMIT 20"
            else:
                cosmos_query = "SELECT * FROM c OFFSET 0 LIMIT 20"
                params = []

            rows: List[Dict[str, Any]] = []
            async for item in container.query_items(
                query=cosmos_query,
                parameters=params if params else None,
                enable_cross_partition_query=True,
            ):
                rows.append(item)

            citations = [
                Citation(
                    source_type="NOSQL",
                    identifier=f"cosmos-notams-{len(rows)}",
                    title=f"NOTAMs query: {query[:60]}",
                    content_preview=f"{len(rows)} NOTAMs found",
                    score=1.0,
                    dataset="cosmos_notams",
                )
            ]
            return rows, citations

        except Exception as e:
            logger.error("Cosmos query failed: %s", e)
            return [], [Citation(source_type="NOSQL", title=f"Cosmos error: {str(e)[:100]}")]

    async def _get_cosmos_container(self, endpoint, key, db_name, container_name):
        if self._cosmos_container is None:
            if key:
                self._cosmos_client = AsyncCosmosClient(endpoint, credential=key)
            else:
                from azure.identity.aio import DefaultAzureCredential as AsyncDefaultCredential
                self._cosmos_credential = AsyncDefaultCredential()
                self._cosmos_client = AsyncCosmosClient(endpoint, credential=self._cosmos_credential)
            db = self._cosmos_client.get_database_client(db_name)
            self._cosmos_container = db.get_container_client(container_name)
        return self._cosmos_container

    # ------------------------------------------------------------------
    # 8. FABRIC_SQL (Fabric SQL Warehouse — BTS delay data)
    # ------------------------------------------------------------------
    async def query_fabric_sql(
        self,
        query: str,
    ) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Query Fabric SQL Warehouse for BTS on-time performance data."""
        if not self._fabric_sql_endpoint:
            # Try pyodbc TDS fallback
            return await self._query_fabric_sql_tds(query)

        try:
            token = await self._get_fabric_token()
            if not token:
                return [], [Citation(source_type="FABRIC_SQL", title="No Fabric token")]

            # Generate T-SQL via LLM
            tsql = await self._sql_writer.generate(
                user_query=query,
                evidence_type="HistoricalDelays",
                sql_schema={"tables": {
                    "bts_ontime_reporting": {
                        "columns": {
                            "year": "int", "month": "int", "carrier": "varchar",
                            "origin": "varchar", "dest": "varchar",
                            "dep_delay": "float", "arr_delay": "float",
                            "cancelled": "float", "diverted": "float",
                            "carrier_delay": "float", "weather_delay": "float",
                            "nas_delay": "float", "security_delay": "float",
                            "late_aircraft_delay": "float",
                        }
                    }
                }},
                entities={"airports": _extract_airports_from_query(query), "flight_ids": []},
                time_window={"horizon_min": 0},
                constraints={"dialect": "tsql"},
            )

            if not tsql or "NEED_SCHEMA" in tsql:
                return [], [Citation(source_type="FABRIC_SQL", title="Could not generate T-SQL")]

            http = await self._get_http()
            resp = await http.post(
                self._fabric_sql_endpoint,
                json={"query": tsql},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            rows = data.get("results", [])
            citations = [
                Citation(
                    source_type="FABRIC_SQL",
                    identifier=f"fabric-sql-{hash(tsql) % 10000}",
                    title=f"Fabric SQL: {tsql[:80]}",
                    content_preview=f"{len(rows)} rows",
                    score=1.0,
                    dataset="fabric_sql_warehouse",
                )
            ]
            return rows, citations

        except Exception as e:
            logger.error("Fabric SQL query failed: %s", e)
            return [], [Citation(source_type="FABRIC_SQL", title=f"Fabric SQL error: {str(e)[:100]}")]

    async def _query_fabric_sql_tds(self, query: str) -> Tuple[List[Dict[str, Any]], List[Citation]]:
        """Fallback: pyodbc TDS connection wrapped in asyncio.to_thread."""
        try:
            import pyodbc
        except ImportError:
            return [], [Citation(source_type="FABRIC_SQL", title="pyodbc not installed")]

        fabric_conn_str = os.getenv("FABRIC_SQL_CONNECTION_STRING", "")
        if not fabric_conn_str:
            return [], [Citation(source_type="FABRIC_SQL", title="No Fabric SQL connection string")]

        def _sync_query():
            conn = pyodbc.connect(fabric_conn_str)
            cursor = conn.cursor()
            cursor.execute(f"SELECT TOP 50 * FROM bts_ontime_reporting WHERE origin IN ('ORD','ATL','DFW')")
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return rows

        try:
            rows = await asyncio.to_thread(_sync_query)
            citations = [
                Citation(
                    source_type="FABRIC_SQL",
                    title=f"Fabric SQL TDS: {query[:60]}",
                    content_preview=f"{len(rows)} rows",
                    score=0.9,
                    dataset="fabric_sql_tds",
                )
            ]
            return rows, citations
        except Exception as e:
            logger.error("Fabric SQL TDS failed: %s", e)
            return [], [Citation(source_type="FABRIC_SQL", title=f"TDS error: {str(e)[:100]}")]

    # ------------------------------------------------------------------
    # Embedding helper
    # ------------------------------------------------------------------
    async def get_embedding(self, text: str) -> List[float]:
        """Get text embedding from Azure OpenAI."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        try:
            from data_sources.azure_client import get_shared_async_client
            client, _ = await get_shared_async_client(api_version=OPENAI_API_VERSION)
            response = await client.embeddings.create(
                model=self._embedding_deployment,
                input=text,
            )
            if not response.data:
                logger.warning("Empty embedding response for text: %s", text[:50])
                return []
            embedding = response.data[0].embedding
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.warning("Embedding generation failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Multi-source parallel query
    # ------------------------------------------------------------------
    async def query_multiple(
        self,
        query: str,
        sources: List[str],
        **kwargs,
    ) -> Dict[str, Tuple[List[Dict[str, Any]], List[Citation]]]:
        """Query multiple sources in parallel. Returns {source: (rows, citations)}."""
        source_methods = {
            "SQL": self.query_sql,
            "KQL": self.query_kql,
            "GRAPH": self.query_graph,
            "VECTOR_OPS": lambda q, **kw: self.query_semantic(q, source="VECTOR_OPS", **kw),
            "VECTOR_REG": lambda q, **kw: self.query_semantic(q, source="VECTOR_REG", **kw),
            "VECTOR_AIRPORT": lambda q, **kw: self.query_semantic(q, source="VECTOR_AIRPORT", **kw),
            "NOSQL": self.query_nosql,
            "FABRIC_SQL": self.query_fabric_sql,
        }

        tasks = {}
        for source in sources:
            method = source_methods.get(source)
            if method:
                tasks[source] = asyncio.create_task(method(query, **kwargs))

        results = {}
        for source, task in tasks.items():
            try:
                results[source] = await task
            except Exception as e:
                logger.error("Source %s failed: %s", source, e)
                results[source] = ([], [Citation(source_type=source, title=f"Error: {str(e)[:80]}")])

        return results


# ---------------------------------------------------------------------------
# Singleton retriever instance
# ---------------------------------------------------------------------------

_retriever: Optional[AsyncUnifiedRetriever] = None
_retriever_lock = asyncio.Lock()


async def get_retriever(pg_pool=None) -> AsyncUnifiedRetriever:
    """Get or create the singleton retriever instance (async-safe)."""
    global _retriever
    if _retriever is not None:
        if pg_pool is not None and _retriever._pg_pool is None:
            logger.warning("Retriever singleton already exists without pg_pool; updating pool")
            _retriever._pg_pool = pg_pool
            _retriever._schema_provider = AsyncSchemaProvider(pg_pool=pg_pool)
        return _retriever
    async with _retriever_lock:
        if _retriever is None:
            _retriever = AsyncUnifiedRetriever(pg_pool=pg_pool)
        return _retriever
