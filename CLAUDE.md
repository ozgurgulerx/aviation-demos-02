# Claude Code Project Instructions

## Critical Rules

### DATABASE PROTECTION - ABSOLUTE & NON-NEGOTIABLE
- ❌ **DO NOT** alter, modify, delete, or change ANYTHING in existing databases
- ❌ **DO NOT** run ANY DDL commands (ALTER, DROP, TRUNCATE) on existing schemas
- ✅ This project uses the `aviation_solver` schema - create new, do not modify existing
- ✅ Only SELECT (read) from existing tables - nothing else

### AZURE POSTGRESQL PROTECTION
The database at `aviationragpg705508.postgres.database.azure.com` is **STRICTLY READ-ONLY**:
- NEVER execute: INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, TRUNCATE on existing schemas
- This project creates its own `aviation_solver` schema only

### DO NOT MODIFY
- **fund-rag namespace on AKS** - Do not touch
- **ic-autopilot namespace on aks-fund-rag** - Do not touch
- **rg-fund-rag resource group** - Do not modify existing resources
- **rg-emrgpay resource group** - Different project, do not touch

## Project Structure

```
aviation-demos-02/
├── backend/          # FastAPI backend (port 5002)
│   ├── agents/       # ChatAgent implementations (flight_analyst, operations_advisor, safety_inspector)
│   │   └── tools/    # @ai_function stub tools
│   ├── orchestrator/ # Workflow engine, builders, executors
│   ├── schemas/      # Pydantic models (events, runs)
│   ├── services/     # Redis event bus, PostgreSQL run store
│   └── migrations/   # SQL migrations (aviation_solver schema)
├── frontend/         # Next.js 15 frontend (port 3002)
│   ├── app/api/av/   # API proxy routes
│   ├── components/av/# Aviation-specific components
│   ├── hooks/        # SSE hook with reconnection
│   └── store/        # Zustand state management
├── k8s/              # Kubernetes manifests
├── infra/            # Helm charts and scripts
├── tests/            # Test suite
└── .github/workflows/# CI/CD pipelines
```

## Agent Framework Architecture

Uses Microsoft Agent Framework for Python (`agent-framework-core`).

### Agents (`backend/agents/`)
- **ChatAgent**: Core agent class from Agent Framework
- **AzureOpenAIChatClient**: Azure OpenAI integration with credential fallback
- **@ai_function decorator**: Tool/function definitions

Agents:
- `flight_analyst.py` - Flight data analysis, schedule disruption patterns
- `operations_advisor.py` - Operations optimization, resource allocation
- `safety_inspector.py` - Safety compliance, risk assessment, solution validation

### Model Deployments
- **Agents**: `gpt-5-nano` (AZURE_OPENAI_AGENT_DEPLOYMENT)
- **Orchestrator**: `gpt-5-mini` (AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT)

### Orchestration Patterns (`backend/orchestrator/`)
| Type | Builder | Description |
|------|---------|-------------|
| `sequential` | `SequentialBuilder` | Linear: FlightAnalyst → OperationsAdvisor → SafetyInspector |
| `handoff` | `HandoffBuilder` | Coordinator delegates to specialists |

### Event Flow
- Workflow events stream via Redis Streams (prefix: `av:events:`)
- SSE endpoint: `/api/av/runs/{run_id}/events`
- Schema: `aviation_solver` in PostgreSQL

### API Endpoints
- `POST /api/av/solve` - Start a solver run
- `POST /api/av/chat` - Chat with advisor
- `GET /api/av/runs/{run_id}/events` - SSE event stream
- `GET /api/av/runs/{run_id}` - Run status
- `GET /api/av/runs` - List runs
- `GET /health` - Health check
- `GET /ready` - Readiness check

## Local Development
- **Frontend**: Must run on **port 3002** (`next dev -p 3002`). Port 3001 is used by another project.
- **Backend**: Must run on **port 5002** (`PORT=5002`). Port 5001 is used by another project.

## Environment
- **ACR**: `avrag705508acr.azurecr.io`
- **Backend image**: `aviation-multi-agent-backend`
- **Azure OpenAI**: `aoai-ep-swedencentral02.openai.azure.com`
