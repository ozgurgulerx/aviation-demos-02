# Azure Infrastructure — aviation-demos-02

Multi-agent aviation operations platform. Frontend on App Service, backend on AKS, both in Sweden Central.

## Architecture Diagram

```
                          ┌─────────────────────────────────────────────────────────┐
                          │  Azure Subscription: 6a539906-...                       │
                          │  Tenant: MngEnvMCAP705508                               │
                          │  Resource Group: rg-aviation-rag (Sweden Central)        │
                          │                                                         │
   Internet               │  ┌───────────────────────────────────────────────────┐  │
      │                   │  │  VNet: vnet-aviation-rag  (10.0.0.0/16)          │  │
      │                   │  │                                                   │  │
      ▼                   │  │  ┌─────────────────────────────────────────────┐  │  │
 ┌─────────────┐          │  │  │ subnet-appservice                          │  │  │
 │  App Service │◄─────────┼──┼──│                                           │  │  │
 │  (frontend)  │ VNet     │  │  │  aviation-multiagent-frontend-705508      │  │  │
 │  Next.js 15  │ Integr.  │  │  │  Plan: plan-aviation-rag-frontend (P1V3)  │  │  │
 │  Node 20 LTS │──────────┼──┼──│  Port 3000 · node server.js              │  │  │
 └─────────────┘          │  │  └──────────────────┬──────────────────────────┘  │  │
                          │  │                     │ http://10.0.0.4:80          │  │
                          │  │                     ▼                             │  │
                          │  │  ┌─────────────────────────────────────────────┐  │  │
                          │  │  │ subnet-aks                                  │  │  │
                          │  │  │                                             │  │  │
                          │  │  │  AKS: aks-aviation-rag                     │  │  │
                          │  │  │  Namespace: aviation-multi-agent            │  │  │
                          │  │  │                                             │  │  │
                          │  │  │  ┌──────────────────────┐  ┌────────────┐  │  │  │
                          │  │  │  │ Backend Deployment   │  │ Redis      │  │  │  │
                          │  │  │  │ (2-5 pods, HPA)      │─►│ 7-alpine   │  │  │  │
                          │  │  │  │ FastAPI · Uvicorn     │  │ ClusterIP  │  │  │  │
                          │  │  │  │ Port 5001             │  │ :6379      │  │  │  │
                          │  │  │  └──────┬───────────────┘  └────────────┘  │  │  │
                          │  │  │         │                                   │  │  │
                          │  │  │  ┌──────┴──────────────────────┐           │  │  │
                          │  │  │  │ Internal Load Balancer       │           │  │  │
                          │  │  │  │ 10.0.0.4:80 → backend:5001  │           │  │  │
                          │  │  │  └─────────────────────────────┘           │  │  │
                          │  │  └─────────────────────────────────────────────┘  │  │
                          │  │                                                   │  │
                          │  │  ┌─────────────────────────────────────────────┐  │  │
                          │  │  │ subnet-privateendpoint                      │  │  │
                          │  │  │  PE → PostgreSQL (10.0.5.4)                 │  │  │
                          │  │  └─────────────────────────────────────────────┘  │  │
                          │  └───────────────────────────────────────────────────┘  │
                          │                                                         │
                          │  ┌──────────────────┐  ┌────────────────────────────┐   │
                          │  │ ACR              │  │ Private DNS Zone           │   │
                          │  │ avrag705508acr   │  │ privatelink.postgres...    │   │
                          │  │ .azurecr.io      │  │ → aviationragpg705508     │   │
                          │  └──────────────────┘  └────────────────────────────┘   │
                          └─────────────────────────────────────────────────────────┘

                          External Services
                          ┌────────────────────────────────────────────┐
                          │ Azure OpenAI (Sweden Central)              │
                          │ aoai-ep-swedencentral02.openai.azure.com   │
                          │ Agents: gpt-5-nano · Orch: gpt-5-mini     │
                          ├────────────────────────────────────────────┤
                          │ PostgreSQL Flexible Server (rg-openai)     │
                          │ aviationragpg705508.postgres.database.azure│
                          │ DB: aviationrag · Schema: aviation_solver  │
                          └────────────────────────────────────────────┘
```

## Resource Inventory

| Resource | Name | Location | Notes |
|----------|------|----------|-------|
| Resource Group | `rg-aviation-rag` | Sweden Central | Shared with aviation-demos-01 |
| VNet | `vnet-aviation-rag` | Sweden Central | `10.0.0.0/16`, reused |
| AKS Cluster | `aks-aviation-rag` | Sweden Central | 1-2 nodes, D2als_v6, Azure CNI |
| ACR | `avrag705508acr.azurecr.io` | Sweden Central | Shared, AKS has AcrPull |
| App Service Plan | `plan-aviation-rag-frontend` | Sweden Central | P1V3 Linux, shared |
| App Service | `aviation-multiagent-frontend-705508` | Sweden Central | Next.js 15 standalone |
| PostgreSQL | `aviationragpg705508` | Sweden Central | Flexible Server in `rg-openai` |
| Azure OpenAI | `aoai-ep-swedencentral02` | Sweden Central | gpt-5-nano + gpt-5-mini |

## Network Topology

**Frontend → Backend** path:
1. User hits `https://aviation-multiagent-frontend-705508.azurewebsites.net`
2. App Service serves Next.js; API routes proxy to `BACKEND_URL`
3. VNet integration routes traffic through `subnet-appservice` into the VNet
4. Internal Load Balancer (`10.0.0.4:80`) forwards to backend pods on `:5001`

**Backend → Data** path:
- **Redis**: ClusterIP service `redis:6379` (in-cluster, ephemeral)
- **PostgreSQL**: Private endpoint at `10.0.5.4:5432`, resolved via Private DNS zone
- **Azure OpenAI**: External HTTPS to `aoai-ep-swedencentral02.openai.azure.com`

## Kubernetes Layout

**Namespace**: `aviation-multi-agent`

| Workload | Replicas | Image | Ports |
|----------|----------|-------|-------|
| `aviation-multi-agent-backend` | 2-5 (HPA, 70% CPU) | `avrag705508acr.azurecr.io/aviation-multi-agent-backend` | 5001 |
| `redis` | 1 | `redis:7-alpine` | 6379 |

**Services**:
| Service | Type | Endpoint |
|---------|------|----------|
| `aviation-multi-agent-backend-internal` | LoadBalancer (internal) | `10.0.0.4:80` → `:5001` |
| `aviation-multi-agent-backend` | ClusterIP | `:5001` |
| `redis` | ClusterIP | `:6379` |

**Security**: Non-root containers, read-only root filesystem, NetworkPolicy restricting ingress to App Service subnet, PDB with `minAvailable: 1`.

## CI/CD Pipelines

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| `deploy-backend.yaml` | Push to main (`backend/`, `k8s/`) | Test → Build image → Push to ACR → Deploy to AKS |
| `deploy-frontend.yaml` | Push to main (`frontend/`) | Lint → Build → Zip deploy to App Service |
| `infra-health-check.yaml` | Every 30 min | Auto-start AKS if stopped, verify pod health |

All pipelines use OIDC federated credentials and validate tenant/subscription before any mutation.

## Key Operational Notes

- **Shared resources**: AKS cluster, ACR, App Service plan, and VNet are shared with aviation-demos-01. This project uses its own K8s namespace (`aviation-multi-agent`) and App Service instance.
- **PostgreSQL schema isolation**: Only the `aviation_solver` schema belongs to this project. The database `aviationrag` is shared — never modify other schemas.
- **Lab tenant quirks**: AKS may auto-stop; the health-check workflow handles restarts. The PostgreSQL server may also stop and need manual `az postgres flexible-server start`.
- **Build platform**: Docker images must be built with `--platform linux/amd64` when building on Apple Silicon.
- **Next.js on App Service**: Requires `HOSTNAME=0.0.0.0` app setting — Azure sets HOSTNAME to the container ID by default, which breaks Next.js binding.
