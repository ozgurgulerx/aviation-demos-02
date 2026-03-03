"""
Aviation Multi-Agent Solver API Server - FastAPI with SSE streaming.
Main entry point for the backend API.
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import logging
import structlog

# Load .env from project root (parent of backend/)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from schemas import WorkflowEvent, EventKind, EventLevel, RunStatus
from schemas.runs import RunMetadata
from services.event_bus import get_event_bus, close_event_bus
from services.run_store import get_run_store

# Configure Python stdlib logging so structlog filter_by_level works
logging.basicConfig(format="%(message)s", stream=__import__("sys").stderr, level=logging.INFO)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_data_source_checks(postgres_ready: bool) -> Dict[str, Dict[str, Any]]:
    search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY", "")
    fabric_token_configured = bool(
        os.getenv("FABRIC_BEARER_TOKEN", "").strip()
        or (
            os.getenv("FABRIC_CLIENT_ID", "").strip()
            and os.getenv("FABRIC_CLIENT_SECRET", "").strip()
            and os.getenv("FABRIC_TENANT_ID", "").strip()
        )
    )
    graph_endpoint = os.getenv("FABRIC_GRAPH_ENDPOINT", "").strip()

    return {
        "SQL": {
            "configured": bool(os.getenv("PGHOST", "").strip()),
            "reachable": postgres_ready,
            "detail": "postgres ready" if postgres_ready else "postgres check failed",
        },
        "KQL": {
            "configured": bool(os.getenv("FABRIC_KQL_ENDPOINT", "").strip() and os.getenv("FABRIC_KQL_DATABASE", "").strip()),
            "reachable": bool(os.getenv("FABRIC_KQL_ENDPOINT", "").strip() and os.getenv("FABRIC_KQL_DATABASE", "").strip()),
            "detail": "endpoint+database configured; runtime token resolved per request" if fabric_token_configured else "endpoint/database configured but no explicit fabric auth env set",
        },
        "GRAPH": {
            "configured": bool(graph_endpoint or os.getenv("PGHOST", "").strip()),
            "reachable": bool(graph_endpoint) or postgres_ready,
            "detail": "fabric endpoint configured" if graph_endpoint else "using postgres fallback",
        },
        "VECTOR_OPS": {
            "configured": bool(search_endpoint and search_key and os.getenv("AZURE_SEARCH_INDEX_OPS_NAME", "").strip()),
            "reachable": bool(search_endpoint and search_key and os.getenv("AZURE_SEARCH_INDEX_OPS_NAME", "").strip()),
            "detail": "search endpoint/key/index configured",
        },
        "VECTOR_REG": {
            "configured": bool(search_endpoint and search_key and os.getenv("AZURE_SEARCH_INDEX_REGULATORY_NAME", "").strip()),
            "reachable": bool(search_endpoint and search_key and os.getenv("AZURE_SEARCH_INDEX_REGULATORY_NAME", "").strip()),
            "detail": "search endpoint/key/index configured",
        },
        "VECTOR_AIRPORT": {
            "configured": bool(search_endpoint and search_key and os.getenv("AZURE_SEARCH_INDEX_AIRPORT_NAME", "").strip()),
            "reachable": bool(search_endpoint and search_key and os.getenv("AZURE_SEARCH_INDEX_AIRPORT_NAME", "").strip()),
            "detail": "search endpoint/key/index configured",
        },
        "NOSQL": {
            "configured": bool(os.getenv("AZURE_COSMOS_ENDPOINT", "").strip()),
            "reachable": bool(os.getenv("AZURE_COSMOS_ENDPOINT", "").strip()),
            "detail": "cosmos endpoint configured" if os.getenv("AZURE_COSMOS_ENDPOINT", "").strip() else "cosmos endpoint missing",
        },
        "FABRIC_SQL": {
            "configured": bool(os.getenv("FABRIC_SQL_ENDPOINT", "").strip() or os.getenv("FABRIC_SQL_CONNECTION_STRING", "").strip()),
            "reachable": bool(os.getenv("FABRIC_SQL_ENDPOINT", "").strip() or os.getenv("FABRIC_SQL_CONNECTION_STRING", "").strip()),
            "detail": "fabric sql endpoint/connection configured" if (os.getenv("FABRIC_SQL_ENDPOINT", "").strip() or os.getenv("FABRIC_SQL_CONNECTION_STRING", "").strip()) else "fabric sql endpoint/connection missing",
        },
    }


def _normalize_workflow_event_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    payload_preview = " ".join(str(payload).split())[:300]
    return {
        "message": payload_preview,
        "raw_payload_preview": payload_preview,
        "payload_type": type(payload).__name__,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup resources."""
    logger.info("starting_aviation_solver_api")
    # Warm Azure OpenAI client cache so first workflow doesn't pay credential cost
    try:
        from agents.client import get_shared_chat_client, get_orchestrator_chat_client
        await asyncio.wait_for(asyncio.to_thread(get_shared_chat_client), timeout=30)
        await asyncio.wait_for(asyncio.to_thread(get_orchestrator_chat_client), timeout=30)
        logger.info("azure_openai_clients_warmed")
    except Exception as e:
        logger.warning("client_warmup_failed", error=str(e))

    # Wire data retriever to all agent tool modules
    retriever = None
    try:
        run_store = await asyncio.wait_for(get_run_store(), timeout=30)
        from data_sources.unified_retriever import get_retriever
        retriever = await asyncio.wait_for(get_retriever(pg_pool=run_store.pool), timeout=15)
        from agents.tools import RETRIEVER_MODULES
        wired = 0
        for mod in RETRIEVER_MODULES:
            if hasattr(mod, "set_retriever"):
                mod.set_retriever(retriever)
                wired += 1
        logger.info("retriever_wired_to_tools", modules_wired=wired)
        try:
            logger.info("data_source_startup_diagnostics", checks=retriever.get_source_diagnostics())
        except Exception as diag_err:
            logger.warning("data_source_startup_diagnostics_failed", error=str(diag_err))
    except Exception as e:
        logger.warning("retriever_wiring_failed", error=str(e))

    yield

    logger.info("shutting_down_aviation_solver_api")
    if retriever:
        try:
            await retriever.close()
            logger.info("retriever_closed")
        except Exception as e:
            logger.warning("retriever_close_failed", error=str(e))
    await close_event_bus()


# Create FastAPI app
app = FastAPI(
    title="Aviation Multi-Agent Solver API",
    description="Aviation domain multi-agent problem solver with real-time workflow orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure telemetry
from telemetry import configure_telemetry, get_current_trace_context
configure_telemetry(app)

# CORS configuration
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] if _cors_origins_env else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Last-Event-ID"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class SolveRequest(BaseModel):
    """Request to start a new solver run."""
    problem: str
    workflow_type: Optional[str] = "sequential"
    orchestration_mode: Optional[str] = None
    max_executor_invocations: Optional[int] = None
    autonomous_turn_limits: Optional[dict[str, int]] = None
    config: Optional[dict] = None


WORKFLOW_SMOKE_CASES = [
    {
        "id": "ui-handoff-llm-directed",
        "workflow_type": "handoff",
        "orchestration_mode": "llm_directed",
        "problem": (
            "Severe thunderstorm at Chicago O'Hare (ORD) has caused a ground stop. "
            "47 flights are delayed or cancelled, affecting approximately 6,800 passengers. "
            "12 aircraft are grounded, 3 runways closed. Develop a recovery plan to minimize "
            "total delay and passenger impact while maintaining crew legality and safety compliance."
        ),
    },
    {
        "id": "ui-handoff-deterministic",
        "workflow_type": "handoff",
        "orchestration_mode": "deterministic",
        "problem": (
            "Flight AA1847 (B737-800, N735AA) is en route from JFK to ORD and is "
            "severely delayed by weather at the destination. Fuel remaining is 90 minutes. "
            "The destination visibility is below minimums with thunderstorms. Recommend the "
            "best diversion and recovery alternative."
        ),
    },
    {
        "id": "ui-sequential",
        "workflow_type": "sequential",
        "problem": (
            "Aviation incident simulation: Gate gate-handoff at JFK for mixed baggage and "
            "maintenance exceptions. Create a safe, practical recovery recommendation with "
            "passenger communication and resource balancing."
        ),
    },
]


def _get_workflow_catalog():
    """Return workflow IDs and sample payloads used by UI and validation tooling."""
    return [
        case.copy()
        for case in WORKFLOW_SMOKE_CASES
    ]


class AgentInfo(BaseModel):
    """Agent metadata for frontend canvas."""
    id: str
    name: str
    icon: str = ""
    color: str = ""
    dataSources: list[str] = []
    included: bool = True
    reason: str = ""
    description: str = ""
    outputs: list[str] = []
    category: str = "specialist"


class SolveResponse(BaseModel):
    """Response after starting a solver run."""
    run_id: str
    status: str
    message: str
    scenario: str = ""
    agents: list[AgentInfo] = []


class ChatRequest(BaseModel):
    """Request for chat interaction."""
    message: str
    run_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from chat interaction."""
    response: str
    run_id: Optional[str] = None


# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for k8s probes."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/ready")
async def readiness_check():
    """Readiness check - verifies dependencies."""
    checks = {"api": True}

    try:
        event_bus = await get_event_bus()
        await event_bus.redis.ping()
        checks["redis"] = True
    except Exception as e:
        checks["redis"] = False
        logger.error("redis_health_check_failed", error=str(e))

    try:
        run_store = await get_run_store()
        async with run_store.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = True
    except Exception as e:
        checks["postgres"] = False
        logger.error("postgres_health_check_failed", error=str(e))

    data_source_checks = _build_data_source_checks(postgres_ready=bool(checks.get("postgres")))
    checks["data_sources"] = data_source_checks

    base_ready = bool(checks.get("api")) and bool(checks.get("redis")) and bool(checks.get("postgres"))
    strict_data_source_readiness = _env_enabled("STRICT_DATA_SOURCE_READINESS", False)
    if strict_data_source_readiness:
        sources_ready = all(
            bool(status.get("configured")) and bool(status.get("reachable"))
            for status in data_source_checks.values()
        )
    else:
        sources_ready = True

    all_healthy = base_ready and sources_ready
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "ready": all_healthy,
            "checks": checks,
            "strict_data_source_readiness": strict_data_source_readiness,
        },
    )


# ============================================================================
# Solver Endpoints
# ============================================================================

@app.post("/api/av/solve", response_model=SolveResponse)
async def start_solve(request: SolveRequest, background_tasks: BackgroundTasks):
    """
    Start a new aviation problem solver run.

    Creates the run record, initializes stages, and starts the workflow.
    Returns immediately with run_id and agent metadata for the canvas UI.
    """
    try:
        from orchestrator.agent_registry import select_agents_for_problem, detect_scenario

        run_store = await get_run_store()

        # Detect scenario and select agents upfront for the response
        scenario = detect_scenario(request.problem)
        selected, excluded = select_agents_for_problem(request.problem)
        agent_infos = []
        for a in selected:
            agent_infos.append(AgentInfo(
                id=a.agent_id, name=a.agent_name, icon=a.icon,
                color=a.color, dataSources=a.data_sources,
                included=True, reason=a.reason,
                description=a.description, outputs=a.outputs,
                category=a.category,
            ))
        for a in excluded:
            agent_infos.append(AgentInfo(
                id=a.agent_id, name=a.agent_name, icon=a.icon,
                color=a.color, dataSources=a.data_sources,
                included=False, reason=a.reason,
                description=a.description, outputs=a.outputs,
                category=a.category,
            ))

        workflow_type = request.workflow_type or "handoff"
        config = request.config or {}
        orchestration_mode = request.orchestration_mode
        if orchestration_mode is None:
            raw_mode = config.get("orchestration_mode")
            if isinstance(raw_mode, str):
                orchestration_mode = raw_mode
        if orchestration_mode is None and workflow_type == "handoff":
            orchestration_mode = "llm_directed"
        max_executor_invocations = request.max_executor_invocations
        if max_executor_invocations is None:
            raw_limit = config.get("max_executor_invocations")
            if isinstance(raw_limit, int):
                max_executor_invocations = raw_limit
        autonomous_turn_limits = request.autonomous_turn_limits
        if autonomous_turn_limits is None:
            raw_turn_limits = config.get("autonomous_turn_limits")
            if isinstance(raw_turn_limits, dict):
                parsed: dict[str, int] = {}
                for key, value in raw_turn_limits.items():
                    if isinstance(key, str) and isinstance(value, int):
                        parsed[key] = value
                autonomous_turn_limits = parsed

        # Generate stages dynamically from selected agents
        from schemas.runs import StageMetadata
        dynamic_stages = [
            StageMetadata(
                stage_id=a.agent_id,
                stage_name=a.agent_name,
                stage_order=i + 1,
            )
            for i, a in enumerate(selected)
        ]

        run = await run_store.create_run(
            problem_description=request.problem,
            stages=dynamic_stages if dynamic_stages else None,
            config={
                "workflow_type": workflow_type,
                "orchestration_mode": orchestration_mode,
                "scenario": scenario,
                "max_executor_invocations": max_executor_invocations,
                "autonomous_turn_limits": autonomous_turn_limits,
                **config,
            },
        )

        background_tasks.add_task(
            execute_workflow,
            run.run_id,
            request.problem,
            workflow_type,
            orchestration_mode,
            max_executor_invocations,
            autonomous_turn_limits,
        )

        logger.info(
            "solve_started",
            run_id=run.run_id,
            workflow_type=workflow_type,
            orchestration_mode=orchestration_mode,
            scenario=scenario,
        )

        return SolveResponse(
            run_id=run.run_id,
            status="started",
            message=f"Solver run started. Subscribe to /api/av/runs/{run.run_id}/events for progress.",
            scenario=scenario,
            agents=agent_infos,
        )

    except Exception as e:
        logger.error("solve_start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/av/runs/{run_id}")
async def get_run(run_id: str):
    """Get run status and metadata."""
    run_store = await get_run_store()
    run = await run_store.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return run.model_dump()


@app.get("/api/av/runs/{run_id}/events")
async def stream_events(request: Request, run_id: str, since: Optional[str] = None):
    """
    SSE endpoint for real-time workflow events.

    Streams events as they occur. Supports reconnection via 'since' parameter
    or Last-Event-ID header.
    """
    last_event_id = since or request.headers.get("Last-Event-ID")

    logger.info("sse_connection_started", run_id=run_id, last_event_id=last_event_id)

    async def event_generator():
        """Generate SSE events from Redis stream."""
        event_bus = await get_event_bus()

        try:
            async for event in event_bus.subscribe(run_id, last_event_id):
                if await request.is_disconnected():
                    logger.info("sse_client_disconnected", run_id=run_id)
                    break

                yield {
                    "id": event.stream_id or event.event_id,
                    "event": event.kind.value,
                    "data": event.to_sse_data(),
                    "retry": 5000,
                }

        except asyncio.CancelledError:
            logger.info("sse_stream_cancelled", run_id=run_id)
        except Exception as e:
            logger.error("sse_stream_error", run_id=run_id, error=str(e))

    return EventSourceResponse(event_generator())


@app.get("/api/av/runs")
async def list_runs(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List solver runs with optional filters."""
    run_store = await get_run_store()

    status_enum = RunStatus(status) if status else None
    runs = await run_store.list_runs(status_enum, limit, offset)

    return {
        "runs": [r.model_dump() for r in runs],
        "count": len(runs),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/av/inventory")
async def get_agent_inventory():
    """Return full agent inventory with tools, instructions, and scenario mappings."""
    from orchestrator.inventory import get_inventory
    return get_inventory()


@app.get("/api/av/workflows")
async def list_workflows():
    """List canonical workflow variants used by smoke tests and UI-driven runs."""
    return {
        "workflows": _get_workflow_catalog(),
        "count": len(WORKFLOW_SMOKE_CASES),
    }


@app.post("/api/av/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint for natural language interaction.

    Uses a ChatAgent with the orchestrator model to answer questions
    about aviation operations, or about completed runs via run context.
    """
    try:
        from agents import create_decision_coordinator

        agent = create_decision_coordinator(name="chat_advisor")

        # Build context from run if provided
        context_parts: list[str] = []
        if request.run_id:
            run_store = await get_run_store()
            run = await run_store.get_run(request.run_id)
            if run:
                context_parts.append(
                    f"Run {run.run_id} ({run.status.value}): {run.problem_description[:300]}"
                )
                for stage in run.stages:
                    context_parts.append(f"  Stage '{stage.stage_name}': {stage.status.value}")

        context = "\n".join(context_parts)
        prompt = request.message
        if context:
            prompt = f"Context from run:\n{context}\n\nUser question: {request.message}"

        response_text = await agent.run(prompt)

        return ChatResponse(
            response=str(response_text),
            run_id=request.run_id,
        )
    except Exception as e:
        logger.warning("chat_agent_failed", error=str(e))
        return ChatResponse(
            response=f"I received your message about: {request.message[:100]}. "
            "The aviation multi-agent solver is ready to help analyze this problem. "
            "Use the 'Solve' button to start a full analysis.",
            run_id=request.run_id,
        )


# ============================================================================
# Workflow Execution (Background Task)
# ============================================================================

async def execute_workflow(
    run_id: str,
    problem: str,
    workflow_type: str = "sequential",
    orchestration_mode: Optional[str] = None,
    max_executor_invocations: Optional[int] = None,
    autonomous_turn_limits: Optional[dict[str, int]] = None,
):
    """
    Execute the aviation solver workflow for a run.
    This is called as a background task and emits events via Redis.
    """
    from orchestrator.engine import OrchestratorEngine

    logger.info(
        "workflow_execution_started",
        run_id=run_id,
        workflow_type=workflow_type,
        orchestration_mode=orchestration_mode,
    )

    run_store = None
    event_bus = None

    try:
        run_store = await get_run_store()
        event_bus = await get_event_bus()

        await run_store.update_run_status(run_id, RunStatus.RUNNING)

        # Emit run started event
        await event_bus.publish(WorkflowEvent(
            run_id=run_id,
            kind=EventKind.RUN_STARTED,
            message=f"Aviation solver started with {workflow_type} workflow",
            payload={
                "workflow_type": workflow_type,
                "orchestration_mode": orchestration_mode,
                "problem": problem[:200],
            },
        ))

        def resolve_event_kind(event_type: str) -> EventKind:
            """Resolve orchestrator callback event types into public SSE event kinds."""
            try:
                return EventKind(event_type)
            except ValueError:
                pass

            aliases = {
                "agent.completed": EventKind.AGENT_COMPLETED_DOT,
                "agent.started": EventKind.AGENT_STARTED_DOT,
                "agent.streaming": EventKind.AGENT_STREAMING,
                "agent.objective": EventKind.AGENT_OBJECTIVE,
                "agent.progress": EventKind.AGENT_PROGRESS,
                "tool.called": EventKind.TOOL_CALLED_DOT,
                "tool.completed": EventKind.TOOL_COMPLETED_DOT,
                "tool.failed": EventKind.TOOL_FAILED_DOT,
                "workflow.started": EventKind.WORKFLOW_STATUS,
                "workflow.output": EventKind.WORKFLOW_STATUS,
                "workflow.failed": EventKind.RUN_FAILED,
                "executor.invoked": EventKind.EXECUTOR_INVOKED,
                "executor.completed": EventKind.EXECUTOR_COMPLETED,
                "orchestrator.workflow_created": EventKind.WORKFLOW_STATUS,
                "orchestrator.run_started": EventKind.RUN_STARTED,
                "orchestrator.run_completed": EventKind.WORKFLOW_STATUS,
                "orchestrator.run_failed": EventKind.RUN_FAILED,
                "coordinator.scoring": EventKind.COORDINATOR_SCORING,
                "coordinator.plan": EventKind.COORDINATOR_PLAN,
                "recovery.option": EventKind.RECOVERY_OPTION,
            }
            if event_type in aliases:
                return aliases[event_type]

            if event_type in {"agent.failed", "executor.failed"}:
                # Keep explicit handling of explicit failure channels aligned with known workflow contracts.
                # Unknown suffix-matching failures should not be promoted to terminal run failure.
                return EventKind.WORKFLOW_STATUS if event_type.startswith("workflow.") else EventKind.PROGRESS_UPDATE
            if event_type.startswith("workflow."):
                return EventKind.WORKFLOW_STATUS
            return EventKind.PROGRESS_UPDATE

        # Create event emitter callback
        async def emit_event(event_type: str, payload: Any):
            payload = _normalize_workflow_event_payload(payload)
            event_kind = resolve_event_kind(event_type)
            event_level = EventLevel.ERROR if event_kind == EventKind.RUN_FAILED else EventLevel.INFO
            message = (
                payload.get("message")
                or payload.get("reasoning")
                or payload.get("summary")
                or payload.get("resultSummary")
                or str(event_type)
            )

            otel_context = get_current_trace_context() or {}
            trace_id = (
                payload.get("trace_id")
                or payload.get("traceId")
                or otel_context.get("trace_id")
            )
            span_id = (
                payload.get("span_id")
                or payload.get("spanId")
                or otel_context.get("span_id")
            )
            parent_span_id = (
                payload.get("parent_span_id")
                or payload.get("parentSpanId")
                or otel_context.get("parent_span_id")
            )

            actor = payload.get("actor")
            if not isinstance(actor, dict):
                actor = {"kind": "orchestrator", "id": "orchestrator", "name": "Orchestrator"}

            await event_bus.publish(WorkflowEvent(
                run_id=run_id,
                kind=event_kind,
                level=event_level,
                message=message,
                stage_id=payload.get("stage_id"),
                stage_name=payload.get("stage_name"),
                agent_name=payload.get("agentName") or payload.get("agent_name"),
                executor_name=payload.get("executor_name") or payload.get("executor_id"),
                tool_name=payload.get("toolName") or payload.get("tool_name"),
                actor=actor,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                payload={
                    "event_type": event_type,
                    "workflow_type": workflow_type,
                    "orchestration_mode": orchestration_mode,
                    **payload,
                },
            ))

        # Create and run orchestrator
        orchestrator = OrchestratorEngine(
            run_id=run_id,
            event_emitter=emit_event,
            workflow_type=workflow_type,
            orchestration_mode=orchestration_mode,
            max_executor_invocations=max_executor_invocations,
            autonomous_turn_limits=autonomous_turn_limits,
        )

        result = await orchestrator.run(problem)

        # Update run status
        await run_store.update_run_status(run_id, RunStatus.COMPLETED)

        # Emit completion with summary for the UI
        answer = ""
        summary = ""
        if isinstance(result, dict):
            answer = str(result.get("answer", "") or "").strip()
            summary = str(result.get("summary", "") or "").strip()
            if not summary:
                summary = f"Analysis complete. {result.get('evidence_count', 0)} evidence items collected."
            if not answer:
                answer = summary
        if not answer:
            answer = f"Aviation solver completed using {workflow_type} workflow."

        await event_bus.publish(WorkflowEvent(
            run_id=run_id,
            kind=EventKind.RUN_COMPLETED,
            message=answer,
            payload={
                "result": result,
                "answer": answer,
                "summary": summary,
                "workflow_type": workflow_type,
                "orchestration_mode": orchestration_mode,
            },
        ))

        logger.info("workflow_execution_completed", run_id=run_id)

    except Exception as e:
        logger.error("workflow_execution_failed", run_id=run_id, error=str(e))

        try:
            if run_store:
                await run_store.update_run_status(run_id, RunStatus.FAILED, error_message=str(e))
            if event_bus:
                await event_bus.publish(WorkflowEvent(
                    run_id=run_id,
                    kind=EventKind.RUN_FAILED,
                    level="error",
                    message=f"Solver run failed: {type(e).__name__}: {str(e)}",
                    payload={
                        "error": f"{type(e).__name__}: {str(e)}",
                        "workflow_type": workflow_type,
                        "orchestration_mode": orchestration_mode,
                    },
                ))
        except Exception as cleanup_err:
            logger.error(
                "workflow_cleanup_failed",
                run_id=run_id,
                original_error=str(e),
                cleanup_error=str(cleanup_err),
            )


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "5001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
