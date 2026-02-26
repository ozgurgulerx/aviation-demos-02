# Infrastructure & Deployment Guide — aviation-demos-02

Multi-agent orchestration platform deployed to Azure (AKS + App Service).

---

## 1. Azure Tenant & Subscription

| Field | Value |
|-------|-------|
| Tenant ID | `52095a81-130f-4b06-83f1-9859b2c73de6` |
| Tenant Name | MngEnvMCAP705508.onmicrosoft.com |
| Subscription ID | `6a539906-6ce2-4e3b-84ee-89f701de18d8` |
| Admin | admin@MngEnvMCAP705508.onmicrosoft.com |

**Tenant lock**: Every provisioning script, CI/CD workflow, and render script validates the active Azure CLI tenant and subscription before making changes.

---

## 2. Resource Groups

| Resource Group | Location | Purpose |
|----------------|----------|---------|
| `rg-aviation-rag` | Sweden Central | Shared RG — reused from aviation-demos-01 (AKS, ACR, App Service plan) |
| `rg-pii-multiagent` | *(legacy)* | Previous shared cluster — do not use |
| `rg-fund-rag` | *(shared)* | **DO NOT MODIFY** — different project |
| `rg-emrgpay` | *(shared)* | **DO NOT MODIFY** — different project |

---

## 3. Networking

### VNet: `vnet-aviation-rag`

Address space: `10.0.0.0/16` (reused from aviation-demos-01)

| Subnet | CIDR | Purpose |
|--------|------|---------|
| `subnet-aks` | `10.2.0.0/22` | AKS node pool (Azure CNI) |
| `subnet-appservice` | `10.2.4.0/24` | App Service VNet integration |
| `subnet-privateendpoint` | `10.2.5.0/24` | Future private endpoints (PG, Redis) |

| AKS Network Config | Value |
|---------------------|-------|
| Service CIDR | `10.3.0.0/16` |
| DNS Service IP | `10.3.0.10` |
| Network Plugin | Azure CNI |

### Network Flow

```
Internet
  │
  ├─► App Service (frontend)  ──VNet Integration──► Internal LB (10.2.x.x:80)
  │     subnet-appservice                              │
  │                                                    ▼
  │                                            AKS Backend Pods (:5001)
  │                                                    │
  │                                                    ├──► Redis (ClusterIP :6379)
  │                                                    ├──► PostgreSQL (external, :5432)
  │                                                    └──► Azure OpenAI (external, HTTPS)
  │
  └─► Ingress Controller (optional)  ──► AKS Backend Pods (:5001)
```

---

## 4. Container Registry

| Field | Value |
|-------|-------|
| ACR Name | `avrag705508acr` |
| Login Server | `avrag705508acr.azurecr.io` |
| Status | **Reused** (shared across projects in rg-aviation-rag) |
| Images | `aviation-multi-agent-backend` |

AKS has `AcrPull` via managed identity. CI/CD has `AcrPush` via OIDC service principal.

---

## 5. AKS Cluster

| Field | Value |
|-------|-------|
| Name | `aks-aviation-rag` |
| Resource Group | `rg-aviation-rag` |
| Location | Sweden Central |
| Node VM Size | `Standard_D2als_v6` |
| Node Count | 1–2 (autoscaler) |
| Network Plugin | Azure CNI |
| Identity | System-assigned managed identity |

### kubectl Setup

```bash
# Option 1: Use the helper script
./infra/scripts/use-deploy-target-context.sh

# Option 2: Manual
az aks get-credentials --resource-group rg-aviation-rag --name aks-aviation-rag
```

### Verify

```bash
kubectl get nodes
kubectl get pods -n aviation-multi-agent
```

---

## 6. Kubernetes Manifests

All manifests in `k8s/` are **envsubst templates**. Render before applying:

```bash
./infra/scripts/render-k8s-manifests.sh
# Output: k8s/rendered/
```

### Apply Order

```bash
kubectl apply -f k8s/rendered/namespace.yaml
kubectl apply -f k8s/rendered/backend-serviceaccount.yaml
kubectl apply -f k8s/rendered/backend-service.yaml
kubectl apply -f k8s/rendered/backend-secret.yaml
kubectl apply -f k8s/rendered/backend-configmap.yaml
kubectl apply -f k8s/rendered/redis-deployment.yaml
kubectl apply -f k8s/rendered/backend-deployment.yaml
kubectl apply -f k8s/rendered/backend-hpa.yaml
kubectl apply -f k8s/rendered/backend-networkpolicy.yaml
kubectl apply -f k8s/rendered/backend-pdb.yaml
kubectl apply -f k8s/rendered/ingress.yaml
```

### Manifest Inventory

| Manifest | Kind | Description |
|----------|------|-------------|
| `namespace.yaml` | Namespace | `aviation-multi-agent` |
| `backend-serviceaccount.yaml` | ServiceAccount | Backend pod identity |
| `backend-configmap.yaml` | ConfigMap | All non-secret config (OpenAI, PG, Redis, Uvicorn, tenant guardrails) |
| `backend-secret.yaml` | Secret | `AZURE_OPENAI_API_KEY`, `PGPASSWORD` |
| `backend-deployment.yaml` | Deployment | Backend pods with security hardening, probes, anti-affinity |
| `backend-service.yaml` | Service | Internal LB + ClusterIP |
| `backend-hpa.yaml` | HPA | CPU-based autoscaling (2–5 replicas, 70% target) |
| `backend-networkpolicy.yaml` | NetworkPolicy | Restrict ingress to App Service subnet, ingress-nginx, same-namespace |
| `backend-pdb.yaml` | PDB | `minAvailable: 1` |
| `redis-deployment.yaml` | Deployment + Service | Redis 7 Alpine with probes and security context |
| `ingress.yaml` | Ingress | NGINX ingress with SSE/CORS support |

### Security Hardening (backend-deployment.yaml)

- `runAsNonRoot: true`, `runAsUser: 1000`, `fsGroup: 1000`
- `readOnlyRootFilesystem: true` (with `/tmp` emptyDir mount)
- `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`
- Rolling update: `maxSurge: 1`, `maxUnavailable: 0`
- Startup probe (480s budget), liveness probe, readiness probe (`/ready`)
- Pod anti-affinity (prefer spread across nodes)
- `terminationGracePeriodSeconds: 60`

---

## 7. App Service (Frontend)

| Field | Value |
|-------|-------|
| Name | `aviation-multiagent-frontend-705508` |
| Plan | `plan-aviation-rag-frontend` (P1V3, Linux, reused) |
| Runtime | Node.js 20 LTS |
| URL | `https://aviation-multiagent-frontend-705508.azurewebsites.net` |

### App Settings

| Setting | Value |
|---------|-------|
| `BACKEND_URL` | Internal LB IP (e.g., `http://10.2.0.x`) |
| `PORT` | `3000` |
| `WEBSITES_PORT` | `3000` |
| `WEBSITE_VNET_ROUTE_ALL` | `1` |
| Startup Command | `node server.js` |

### VNet Integration

App Service is integrated with `subnet-appservice` (`10.2.4.0/24`), routing all traffic through the VNet. This allows it to reach the AKS internal load balancer.

---

## 8. PostgreSQL

| Field | Value |
|-------|-------|
| Server | `aviationragpg705508.postgres.database.azure.com` |
| Database | `aviationrag` |
| Schema | `aviation_solver` |
| User | `pgadmin` |
| Status | **Shared / READ-ONLY** for existing schemas |

**CRITICAL**: Only the `aviation_solver` schema belongs to this project. Never ALTER/DROP/TRUNCATE existing schemas or tables.

### Migrations

SQL migration files are in `backend/migrations/`. Run via:
- GitHub Actions: `migrate-database.yaml` (requires typing "migrate" as confirmation)
- Manual: `psql` or `asyncpg` against the migration files

---

## 9. Redis

| Field | Value |
|-------|-------|
| Type | In-cluster (AKS) |
| Image | `redis:7-alpine` |
| Persistence | Ephemeral (emptyDir) — AOF enabled within pod lifetime |
| Max Memory | 200MB (allkeys-lru eviction) |
| Service | `redis:6379` (ClusterIP) |

Redis is used for event streaming (Redis Streams, prefix `av:events:`). Data is ephemeral and will be lost on pod restart.

---

## 10. Azure OpenAI

| Field | Value |
|-------|-------|
| Endpoint | `https://aoai-ep-swedencentral02.openai.azure.com/` |
| Agent Deployment | `gpt-5-nano` |
| Orchestrator Deployment | `gpt-5-mini` |
| API Version | `2025-01-01-preview` |
| Timeout | 120s |
| Max Retries | 3 |

---

## 11. Docker Images

### Backend (`Dockerfile.backend`)

```
Base: python:3.11-slim
User: appuser (UID 1000)
Port: 5001
CMD: uvicorn main:app --host 0.0.0.0 --port 5001 --workers 2
```

Features:
- Non-root user
- `/tmp` writable for readOnlyRootFilesystem
- Health check built into Dockerfile
- Layer-cached pip install

### Frontend (`Dockerfile.frontend`)

Deployed as standalone Next.js build (not containerized). Packaged as a zip and deployed to App Service.

---

## 12. GitHub Actions CI/CD

### Workflows

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Deploy Backend | `deploy-backend.yaml` | Push to main (backend/k8s changes) | Lint → Build → Deploy to AKS |
| Deploy Frontend | `deploy-frontend.yaml` | Push to main (frontend changes) | Lint → Build → Deploy to App Service |
| Infra Health Check | `infra-health-check.yaml` | Every 30 min + manual | Monitor AKS, auto-start if stopped |
| Migrate Database | `migrate-database.yaml` | Manual (requires "migrate" confirmation) | Run SQL migrations |

### Backend Pipeline (3 jobs)

1. **lint-and-test**: Python 3.11, pytest (unit tests only)
2. **build-and-push**: OIDC login → tenant validation → ACR build + push (tagged with SHA)
3. **deploy**: OIDC login → AKS credentials → render manifests → apply → set image → stamp config hashes → rollout monitor (900s timeout, drift detection) → health check via port-forward

### Frontend Pipeline (2 jobs)

1. **lint**: npm ci → next lint
2. **build-and-deploy**: OIDC login → tenant validation → npm build → zip → deploy → configure → verify

---

## 13. GitHub Secrets & Repository Variables

### Secrets

| Secret | Description |
|--------|-------------|
| `AZURE_CLIENT_ID` | OIDC app registration client ID |
| `AZURE_TENANT_ID` | `52095a81-130f-4b06-83f1-9859b2c73de6` |
| `AZURE_SUBSCRIPTION_ID` | `6a539906-6ce2-4e3b-84ee-89f701de18d8` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `PGPASSWORD` | PostgreSQL password |
| `BACKEND_URL` | Internal LB IP (e.g., `http://10.2.0.x`) |

### Repository Variables

| Variable | Value |
|----------|-------|
| `AZURE_RESOURCE_GROUP` | `rg-aviation-rag` |
| `AKS_CLUSTER` | `aks-aviation-rag` |
| `AKS_NAMESPACE` | `aviation-multi-agent` |
| `AZURE_WEBAPP_NAME` | `aviation-multiagent-frontend-705508` |
| `AZURE_CONTAINER_REGISTRY` | `avrag705508acr.azurecr.io` |
| `PGHOST` | `aviationragpg705508.postgres.database.azure.com` |
| `AZURE_OPENAI_ENDPOINT` | `https://aoai-ep-swedencentral02.openai.azure.com/` |

---

## 14. RBAC & Managed Identities

| Identity | Type | Roles |
|----------|------|-------|
| AKS kubelet | System-assigned MI | `AcrPull` on `avrag705508acr` ACR |
| App Service | System-assigned MI | (VNet integration) |
| GitHub OIDC SP | App registration | `Contributor` on `rg-aviation-rag`, `AcrPush` on ACR |

---

## 15. Provisioning Script

### Usage

```bash
# Provision all Azure resources (idempotent)
./infra/scripts/provision-azure.sh

# Also deploy K8s manifests
./infra/scripts/provision-azure.sh --deploy-k8s

# Also setup GitHub OIDC
GITHUB_REPO=owner/repo ./infra/scripts/provision-azure.sh --setup-github-oidc
```

### Environment Variable Overrides

All defaults can be overridden:

```bash
export LOCATION=northeurope
export AKS_VM_SIZE=Standard_D4als_v6
export ASP_SKU=P2V3
./infra/scripts/provision-azure.sh
```

Key defaults:

| Variable | Default |
|----------|---------|
| `LOCATION` | `westeurope` |
| `RESOURCE_GROUP` | `rg-aviation-rag` |
| `VNET_NAME` | `vnet-aviation-rag` |
| `AKS_NAME` | `aks-aviation-rag` |
| `ACR_NAME` | `avrag705508acr` |
| `WEBAPP_NAME` | `aviation-multiagent-frontend-705508` |
| `AKS_VM_SIZE` | `Standard_D2als_v6` |
| `ASP_SKU` | `P1V3` |

---

## 16. Workarounds & Gotchas

### MngEnvMCAP Tenant Policies
This is a managed lab tenant. Some operations may be restricted by tenant policies. The provisioning script is idempotent and safe to re-run.

### SSE Timeouts
Server-Sent Events require long-lived connections. The ingress is configured with 3600s proxy timeouts. The App Service → Internal LB path also needs sufficient timeout configuration.

### Single-worker Uvicorn
The ConfigMap defaults `UVICORN_WORKERS=1`. SSE streaming with agent framework works best with a single worker per pod (scale via HPA replicas instead). The Dockerfile CMD has `--workers 2` as a fallback, but the ConfigMap value takes precedence if the app reads it.

### Shared PostgreSQL
The database is shared with other projects. **Only use the `aviation_solver` schema**. Never modify other schemas. The `fundrag` database belongs to the fund-rag project — we only have a schema within it.

### readOnlyRootFilesystem
The backend container runs with a read-only root filesystem. The `/tmp` directory is mounted as an emptyDir volume to allow temporary file writes. The Dockerfile creates `/tmp` with correct ownership.

---

## 17. Deployment Checklists

### New Environment Setup

1. Run `az login` and verify correct tenant
2. Run `./infra/scripts/provision-azure.sh`
3. Set GitHub secrets and repository variables (see section 13)
4. Run `./infra/scripts/provision-azure.sh --setup-github-oidc` with `GITHUB_REPO` set
5. Run database migrations: trigger `migrate-database.yaml` workflow
6. Push to main to trigger first deployment
7. Set `BACKEND_URL` secret to internal LB IP after first backend deployment
8. Re-run frontend deployment with correct `BACKEND_URL`

### Deploying Changes

**Backend changes:**
1. Push to main (changes in `backend/`, `Dockerfile.backend`, or `k8s/`)
2. `deploy-backend.yaml` runs automatically
3. Monitor the workflow run for rollout status

**Frontend changes:**
1. Push to main (changes in `frontend/`)
2. `deploy-frontend.yaml` runs automatically
3. Verify at `https://aviation-multiagent-frontend-705508.azurewebsites.net`

**Config changes (no code change):**
1. Update ConfigMap/Secret values in render script or GitHub secrets
2. Trigger `deploy-backend.yaml` manually via `workflow_dispatch`

---

## 18. Troubleshooting

### Automated Workflow Smoke Loop

Run repeated smoke runs from the scripts folder after each auth/config fix:

```bash
# Start from a local port-forward to the backend service
kubectl port-forward svc/aviation-multi-agent-backend 5001:5001 -n aviation-multi-agent

# In another shell, run baseline + stability checks
python3 infra/scripts/workflow-smoke-loop.py \
  --backend-url http://127.0.0.1:5001 \
  --rounds 3 \
  --consecutive-success 3 \
  --run-timeout 600 \
  --backend-log-window 20m \
  --round-delay 10
```

Notes:

- The runner first calls `GET /api/av/workflows` to discover current UI/API workflows.
- Artifacts are written to `artifacts/workflow-smoke/<timestamp>/`.
- Each workflow attempt stores:
  - raw SSE events
  - terminal event and error extraction
  - best-effort Azure/AzureOpenAI correlation logs filtered by `run_id`
  - first 10 stderr-like log lines
  - trace context if present

> Requires backend image deployed from the updated code path (tenant lock and workflow
> discovery endpoint must be present in the running image).

### Common Commands

```bash
# Get pod status
kubectl get pods -n aviation-multi-agent

# Pod logs
kubectl logs -f deployment/aviation-multi-agent-backend -n aviation-multi-agent

# Describe pod (for events, startup issues)
kubectl describe pod -l app=aviation-multi-agent-backend -n aviation-multi-agent

# Health check via port-forward
kubectl port-forward svc/aviation-multi-agent-backend 5001:5001 -n aviation-multi-agent
curl http://localhost:5001/health
curl http://localhost:5001/ready

# Redis check
kubectl exec -it deployment/redis -n aviation-multi-agent -- redis-cli ping

# SSE streaming test
curl -N http://localhost:5001/api/av/runs/<run-id>/events

# Internal LB IP
kubectl get svc aviation-multi-agent-backend-internal -n aviation-multi-agent \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# AKS cluster state
az aks show --resource-group rg-aviation-rag --name aks-aviation-rag \
  --query "powerState.code" -o tsv

# Start stopped cluster
az aks start --resource-group rg-aviation-rag --name aks-aviation-rag

# Tenant validation
./infra/scripts/validate-tenant-lock.sh

# View deployment rollout status
kubectl rollout status deployment/aviation-multi-agent-backend -n aviation-multi-agent

# View HPA status
kubectl get hpa -n aviation-multi-agent

# View network policies
kubectl get networkpolicy -n aviation-multi-agent

# View PDB
kubectl get pdb -n aviation-multi-agent
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Pods in CrashLoopBackOff | Check logs: `kubectl logs <pod> -n aviation-multi-agent --previous` |
| ImagePullBackOff | Verify ACR attachment: `az aks check-acr --name aks-aviation-rag --resource-group rg-aviation-rag --acr avrag705508acr.azurecr.io` |
| Internal LB no IP | Wait 2-3 min for Azure LB provisioning. Check `kubectl describe svc aviation-multi-agent-backend-internal -n aviation-multi-agent` |
| Frontend can't reach backend | Verify VNet integration and `BACKEND_URL` matches internal LB IP |
| AKS auto-stopped | Cluster may auto-stop in lab tenants. Health check workflow auto-starts it. |
| readOnlyRootFilesystem errors | Ensure the container writes only to `/tmp`. Check volume mounts. |
