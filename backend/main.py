"""
Aviation Multi-Agent Solver API Server - FastAPI with SSE streaming.
Main entry point for the backend API.
"""

import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup resources."""
    logger.info("starting_aviation_solver_api")
    # Warm Azure OpenAI client cache so first workflow doesn't pay credential cost
    try:
        from agents.client import get_shared_chat_client, get_orchestrator_chat_client
        await asyncio.to_thread(get_shared_chat_client)
        await asyncio.to_thread(get_orchestrator_chat_client)
        logger.info("azure_openai_clients_warmed")
    except Exception as e:
        logger.warning("client_warmup_failed", error=str(e))
    yield
    logger.info("shutting_down_aviation_solver_api")
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


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

    all_healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"ready": all_healthy, "checks": checks},
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
            ))
        for a in excluded:
            agent_infos.append(AgentInfo(
                id=a.agent_id, name=a.agent_name, icon=a.icon,
                color=a.color, dataSources=a.data_sources,
                included=False, reason=a.reason,
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

        run = await run_store.create_run(
            problem_description=request.problem,
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

    Takes a user message and returns a response from the aviation advisor.
    """
    # Simple echo response for now - will be wired to agent in later phase
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
                "orchestrator.run_completed": EventKind.RUN_COMPLETED,
                "orchestrator.run_failed": EventKind.RUN_FAILED,
            }
            if event_type in aliases:
                return aliases[event_type]

            if event_type.endswith(".failed"):
                return EventKind.RUN_FAILED
            if event_type.startswith("workflow."):
                return EventKind.WORKFLOW_STATUS
            return EventKind.PROGRESS_UPDATE

        # Create event emitter callback
        async def emit_event(event_type: str, payload: dict):
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

        # Emit completion
        await event_bus.publish(WorkflowEvent(
            run_id=run_id,
            kind=EventKind.RUN_COMPLETED,
            message=f"Aviation solver completed using {workflow_type} workflow",
            payload={
                "result": result,
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
                    message=f"Solver run failed: {str(e)}",
                    payload={
                        "error": str(e),
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
