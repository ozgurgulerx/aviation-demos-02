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
- **Backend**: Must run on **port 5002** (`PORT=5002` in `.env`). The hardcoded default in `main.py` is `5001` for k8s compatibility.

## Azure Deployment

### Target Tenant (MANDATORY)
- **Tenant ID**: `52095a81-130f-4b06-83f1-9859b2c73de6`
- **Tenant**: `admin@MngEnvMCAP705508.onmicrosoft.com`
- **Subscription ID**: `6a539906-6ce2-4e3b-84ee-89f701de18d8`
- **Resource Group**: `rg-aviation-rag`
- All deployments MUST target this tenant. CI/CD validates tenant on every deploy.

### Infrastructure
- **ACR**: `avrag705508acr.azurecr.io`
- **Backend image**: `aviation-multi-agent-backend`
- **AKS cluster**: `aks-aviation-rag` (namespace: `aviation-multi-agent`)
- **Frontend**: Azure App Service `aviation-multiagent-frontend-705508`
- **Azure OpenAI**: `swedencentral.api.cognitive.microsoft.com`
- **PostgreSQL**: `aviationragpg705508.postgres.database.azure.com` (READ-ONLY for existing schemas)
- **Backend internal URL**: `http://10.0.0.4` (AKS internal LoadBalancer, reachable from App Service via VNet)

### CI/CD (GitHub Actions)
- **Service Principal**: `github-aviation-demos-02-deploy` (app ID: `4c49d528-94ac-425c-bde6-c755f3a4d4e4`)
- Uses OIDC federated credentials (no stored secrets in Azure)
- Backend deploys to AKS on push to `main` (paths: `backend/`, `tests/`, `k8s/`)
- Frontend deploys to App Service on push to `main` (paths: `frontend/`)
- Required GitHub secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_OPENAI_API_KEY`, `PGPASSWORD`, `BACKEND_URL`

### DO NOT MODIFY (other projects)
- **aviation-demos-01** repo and its service principal `github-aviation-rag-deploy` — separate project
- **fund-rag namespace on AKS** — Do not touch
- **ic-autopilot namespace on aks-fund-rag** — Do not touch
- **rg-fund-rag resource group** — Do not modify existing resources
- **rg-emrgpay resource group** — Different project, do not touch
