"""
Run metadata store using PostgreSQL for durable run state.

IMPORTANT DATABASE SAFETY:
- This module ONLY creates and manages tables in the 'aviation_solver' schema
- It does NOT touch any existing schemas
- All operations are isolated to aviation_solver.runs, aviation_solver.stages
"""

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Optional, List
import structlog
import asyncpg
from asyncpg import Pool

from schemas.runs import RunMetadata, RunStatus, StageStatus, StageMetadata, create_new_run

logger = structlog.get_logger()

# PostgreSQL configuration
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "postgres")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PG_SCHEMA = os.getenv("PG_SCHEMA", "aviation_solver")


class RunStore:
    """
    PostgreSQL-based run metadata store.

    Schema:
        aviation_solver.runs - Run metadata
        aviation_solver.stages - Stage checkpoints
    """

    def __init__(self, pool: Pool):
        self.pool = pool

    @classmethod
    async def create(cls) -> "RunStore":
        """Factory method to create RunStore with connection pool."""
        import ssl as _ssl
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE

        pool = await asyncpg.create_pool(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            min_size=2,
            max_size=10,
            ssl=ssl_ctx,
        )

        store = cls(pool)
        await store._init_schema()
        logger.info("run_store_connected", host=PGHOST, database=PGDATABASE)
        return store

    async def _init_schema(self):
        """Initialize database schema if not exists."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA};

                CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.runs (
                    run_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    problem_description TEXT DEFAULT '',
                    config JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    duration_ms INTEGER,
                    current_stage VARCHAR(50),
                    stages_completed INTEGER DEFAULT 0,
                    progress_pct REAL DEFAULT 0,
                    error_message TEXT,
                    error_stage VARCHAR(50),
                    event_count INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{{}}'::jsonb
                );

                CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.stages (
                    run_id VARCHAR(50) REFERENCES {PG_SCHEMA}.runs(run_id) ON DELETE CASCADE,
                    stage_id VARCHAR(50),
                    stage_name VARCHAR(100),
                    stage_order INTEGER,
                    status VARCHAR(20) DEFAULT 'pending',
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    duration_ms INTEGER,
                    progress_pct REAL DEFAULT 0,
                    error_message TEXT,
                    PRIMARY KEY (run_id, stage_id)
                );

                CREATE INDEX IF NOT EXISTS idx_av_runs_status ON {PG_SCHEMA}.runs(status);
                CREATE INDEX IF NOT EXISTS idx_av_runs_created ON {PG_SCHEMA}.runs(created_at DESC);
            """)
            logger.info("run_store_schema_initialized", schema=PG_SCHEMA)

    async def create_run(
        self,
        problem_description: str = "",
        config: dict = None,
    ) -> RunMetadata:
        """Create a new run with default stages."""
        run = create_new_run(problem_description, config)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"""
                    INSERT INTO {PG_SCHEMA}.runs
                    (run_id, problem_description, config)
                    VALUES ($1, $2, $3)
                """, run.run_id, problem_description, json.dumps(config or {}))

                for stage in run.stages:
                    await conn.execute(f"""
                        INSERT INTO {PG_SCHEMA}.stages
                        (run_id, stage_id, stage_name, stage_order)
                        VALUES ($1, $2, $3, $4)
                    """, run.run_id, stage.stage_id, stage.stage_name, stage.stage_order)

        logger.info("run_created", run_id=run.run_id)
        return run

    async def get_run(self, run_id: str) -> Optional[RunMetadata]:
        """Get run metadata by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT * FROM {PG_SCHEMA}.runs WHERE run_id = $1
            """, run_id)

            if not row:
                return None

            run = RunMetadata(
                run_id=row["run_id"],
                status=RunStatus(row["status"]),
                problem_description=row["problem_description"] or "",
                config=json.loads(row["config"]) if row["config"] else {},
                created_at=row["created_at"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                duration_ms=row["duration_ms"],
                current_stage=row["current_stage"],
                stages_completed=row["stages_completed"] or 0,
                progress_pct=row["progress_pct"] or 0,
                error_message=row["error_message"],
                error_stage=row["error_stage"],
                event_count=row["event_count"] or 0,
            )

            stage_rows = await conn.fetch(f"""
                SELECT * FROM {PG_SCHEMA}.stages
                WHERE run_id = $1 ORDER BY stage_order
            """, run_id)

            for srow in stage_rows:
                run.stages.append(StageMetadata(
                    stage_id=srow["stage_id"],
                    stage_name=srow["stage_name"],
                    stage_order=srow["stage_order"],
                    status=StageStatus(srow["status"]),
                    started_at=srow["started_at"],
                    completed_at=srow["completed_at"],
                    duration_ms=srow["duration_ms"],
                    progress_pct=srow["progress_pct"] or 0,
                    error_message=srow["error_message"],
                ))

            return run

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        error_message: str = None,
        error_stage: str = None,
    ):
        """Update run status."""
        async with self.pool.acquire() as conn:
            now = datetime.utcnow()
            updates = {"status": status.value}

            if status == RunStatus.RUNNING:
                updates["started_at"] = now
            elif status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]:
                updates["completed_at"] = now

            if error_message:
                updates["error_message"] = error_message
            if error_stage:
                updates["error_stage"] = error_stage

            set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates.keys()))
            values = [run_id] + list(updates.values())

            await conn.execute(f"""
                UPDATE {PG_SCHEMA}.runs SET {set_clause} WHERE run_id = $1
            """, *values)

    async def update_stage(
        self,
        run_id: str,
        stage_id: str,
        status: StageStatus,
        duration_ms: int = None,
        error_message: str = None,
    ):
        """Update stage status and metadata."""
        async with self.pool.acquire() as conn:
            now = datetime.utcnow()

            if status == StageStatus.RUNNING:
                await conn.execute(f"""
                    UPDATE {PG_SCHEMA}.stages
                    SET status = $3, started_at = $4
                    WHERE run_id = $1 AND stage_id = $2
                """, run_id, stage_id, status.value, now)
            else:
                await conn.execute(f"""
                    UPDATE {PG_SCHEMA}.stages
                    SET status = $3, completed_at = $4, duration_ms = $5, error_message = $6
                    WHERE run_id = $1 AND stage_id = $2
                """, run_id, stage_id, status.value, now, duration_ms, error_message)

            # Update run progress
            completed = await conn.fetchval(f"""
                SELECT COUNT(*) FROM {PG_SCHEMA}.stages
                WHERE run_id = $1 AND status IN ('succeeded', 'skipped')
            """, run_id)
            total = await conn.fetchval(f"""
                SELECT COUNT(*) FROM {PG_SCHEMA}.stages WHERE run_id = $1
            """, run_id)

            progress = (completed / total * 100) if total > 0 else 0
            await conn.execute(f"""
                UPDATE {PG_SCHEMA}.runs
                SET current_stage = $2, stages_completed = $3, progress_pct = $4
                WHERE run_id = $1
            """, run_id, stage_id, completed, progress)

    async def list_runs(
        self,
        status: Optional[RunStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[RunMetadata]:
        """List runs with optional filters."""
        async with self.pool.acquire() as conn:
            conditions = []
            params = []
            param_idx = 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            params.extend([limit, offset])
            rows = await conn.fetch(f"""
                SELECT run_id FROM {PG_SCHEMA}.runs
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """, *params)

            runs = []
            for row in rows:
                run = await self.get_run(row["run_id"])
                if run:
                    runs.append(run)

            return runs

    async def close(self):
        """Close connection pool."""
        await self.pool.close()


# Singleton instance with async-safe lock
_run_store: Optional[RunStore] = None
_run_store_lock = asyncio.Lock()

# Schema name validation — alphanumeric and underscores only
if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', PG_SCHEMA):
    raise ValueError(f"Invalid PG_SCHEMA name: {PG_SCHEMA!r}. Must be alphanumeric/underscores only.")


async def get_run_store() -> RunStore:
    """Get or create the singleton RunStore instance (async-safe)."""
    global _run_store
    if _run_store is not None:
        return _run_store
    async with _run_store_lock:
        if _run_store is None:
            _run_store = await RunStore.create()
        return _run_store
