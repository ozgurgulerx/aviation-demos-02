#!/usr/bin/env bash
# render-k8s-manifests.sh — Renders K8s manifest templates via envsubst
set -euo pipefail

###############################################################################
# Colors
###############################################################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
die()  { err "$@"; exit 1; }

###############################################################################
# Defaults — all overridable via environment
###############################################################################
export K8S_NAMESPACE="${K8S_NAMESPACE:-aviation-multi-agent}"
export APP_NAME="${APP_NAME:-aviation-multi-agent}"
export IMAGE_NAME="${IMAGE_NAME:-aviation-multi-agent-backend}"
export IMAGE_TAG="${IMAGE_TAG:-latest}"
export AZURE_CONTAINER_REGISTRY="${AZURE_CONTAINER_REGISTRY:-avrag705508acr.azurecr.io}"

# Azure OpenAI
export AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-https://swedencentral.api.cognitive.microsoft.com/}"
export AZURE_OPENAI_TENANT_ID="${AZURE_OPENAI_TENANT_ID:-${EXPECTED_RUNTIME_TENANT_ID}}"
export AZURE_OPENAI_AUTH_MODE="${AZURE_OPENAI_AUTH_MODE:-api-key}"
export AZURE_OPENAI_AGENT_DEPLOYMENT="${AZURE_OPENAI_AGENT_DEPLOYMENT:-gpt-5-nano}"
export AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT="${AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT:-gpt-5-mini}"
export AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2025-04-01-preview}"
export AZURE_OPENAI_TIMEOUT_SECONDS="${AZURE_OPENAI_TIMEOUT_SECONDS:-120}"
export AZURE_OPENAI_MAX_RETRIES="${AZURE_OPENAI_MAX_RETRIES:-3}"

# PostgreSQL
export PGHOST="${PGHOST:-aviationragpg705508.postgres.database.azure.com}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-aviationrag}"
export PGUSER="${PGUSER:-pgadmin}"

# Redis
export BACKEND_REDIS_HOST="${BACKEND_REDIS_HOST:-redis}"
export BACKEND_REDIS_PORT="${BACKEND_REDIS_PORT:-6379}"

# App config
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
export UVICORN_TIMEOUT_SECONDS="${UVICORN_TIMEOUT_SECONDS:-120}"
export UVICORN_KEEPALIVE_SECONDS="${UVICORN_KEEPALIVE_SECONDS:-65}"

# Tenant guardrails
export EXPECTED_RUNTIME_TENANT_ID="${EXPECTED_RUNTIME_TENANT_ID:-52095a81-130f-4b06-83f1-9859b2c73de6}"
export EXPECTED_RUNTIME_SUBSCRIPTION_ID="${EXPECTED_RUNTIME_SUBSCRIPTION_ID:-6a539906-6ce2-4e3b-84ee-89f701de18d8}"

# Secrets (must be set externally for actual deployment)
export AZURE_OPENAI_API_KEY="${AZURE_OPENAI_API_KEY:-__PLACEHOLDER__}"
export PGPASSWORD="${PGPASSWORD:-__PLACEHOLDER__}"

# HPA
export HPA_MIN_REPLICAS="${HPA_MIN_REPLICAS:-2}"
export HPA_MAX_REPLICAS="${HPA_MAX_REPLICAS:-5}"
export HPA_CPU_TARGET="${HPA_CPU_TARGET:-70}"

# Network policy
export APPSERVICE_SUBNET_CIDR="${APPSERVICE_SUBNET_CIDR:-10.2.4.0/24}"

###############################################################################
# Tenant/subscription validation
###############################################################################
TARGET_TENANT_ID="${TARGET_TENANT_ID:-52095a81-130f-4b06-83f1-9859b2c73de6}"
TARGET_SUBSCRIPTION_ID="${TARGET_SUBSCRIPTION_ID:-6a539906-6ce2-4e3b-84ee-89f701de18d8}"

if command -v az &>/dev/null && az account show &>/dev/null 2>&1; then
  CURRENT_TENANT=$(az account show --query tenantId -o tsv 2>/dev/null || echo "")
  CURRENT_SUB=$(az account show --query id -o tsv 2>/dev/null || echo "")
  if [[ -n "$CURRENT_TENANT" && "$CURRENT_TENANT" != "$TARGET_TENANT_ID" ]]; then
    die "Tenant mismatch! Current: $CURRENT_TENANT  Expected: $TARGET_TENANT_ID"
  fi
  if [[ -n "$CURRENT_SUB" && "$CURRENT_SUB" != "$TARGET_SUBSCRIPTION_ID" ]]; then
    die "Subscription mismatch! Current: $CURRENT_SUB  Expected: $TARGET_SUBSCRIPTION_ID"
  fi
  log "Azure CLI tenant/subscription validated"
else
  warn "Azure CLI not available or not logged in; skipping tenant validation"
fi

###############################################################################
# Paths
###############################################################################
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_DIR="$PROJECT_ROOT/k8s"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/k8s/rendered}"

mkdir -p "$OUTPUT_DIR"

###############################################################################
# Required variables check
###############################################################################
REQUIRED_VARS=(
  K8S_NAMESPACE APP_NAME IMAGE_NAME IMAGE_TAG AZURE_CONTAINER_REGISTRY
  AZURE_OPENAI_ENDPOINT PGHOST PGDATABASE PGUSER
  EXPECTED_RUNTIME_TENANT_ID EXPECTED_RUNTIME_SUBSCRIPTION_ID
)

MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    MISSING+=("$var")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  die "Missing required variables: ${MISSING[*]}"
fi

###############################################################################
# Explicit variable list for envsubst (prevents clobbering NGINX vars like
# $request_uri, $host, etc. that appear in ingress annotations)
###############################################################################
ENVSUBST_VARS='${K8S_NAMESPACE} ${APP_NAME} ${ENVIRONMENT} ${IMAGE_NAME} ${IMAGE_TAG} ${AZURE_CONTAINER_REGISTRY} ${AZURE_OPENAI_ENDPOINT} ${AZURE_OPENAI_TENANT_ID} ${AZURE_OPENAI_AUTH_MODE} ${AZURE_OPENAI_AGENT_DEPLOYMENT} ${AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT} ${AZURE_OPENAI_API_VERSION} ${AZURE_OPENAI_TIMEOUT_SECONDS} ${AZURE_OPENAI_MAX_RETRIES} ${PGHOST} ${PGPORT} ${PGDATABASE} ${PGUSER} ${BACKEND_REDIS_HOST} ${BACKEND_REDIS_PORT} ${LOG_LEVEL} ${UVICORN_WORKERS} ${UVICORN_TIMEOUT_SECONDS} ${UVICORN_KEEPALIVE_SECONDS} ${EXPECTED_RUNTIME_TENANT_ID} ${EXPECTED_RUNTIME_SUBSCRIPTION_ID} ${AZURE_OPENAI_API_KEY} ${PGPASSWORD} ${HPA_MIN_REPLICAS} ${HPA_MAX_REPLICAS} ${HPA_CPU_TARGET} ${APPSERVICE_SUBNET_CIDR}'

###############################################################################
# Render templates
###############################################################################
echo "=== Rendering K8s manifests ==="
echo "  Templates: $TEMPLATE_DIR"
echo "  Output:    $OUTPUT_DIR"
echo ""

RENDERED=0
for tmpl in "$TEMPLATE_DIR"/*.yaml; do
  [[ -f "$tmpl" ]] || continue
  filename=$(basename "$tmpl")
  envsubst "$ENVSUBST_VARS" < "$tmpl" > "$OUTPUT_DIR/$filename"
  log "Rendered: $filename"
  RENDERED=$((RENDERED + 1))
done

echo ""
log "Rendered $RENDERED manifests to $OUTPUT_DIR"

###############################################################################
# Warn on placeholder secrets
###############################################################################
if [[ "$AZURE_OPENAI_API_KEY" == "__PLACEHOLDER__" ]]; then
  warn "AZURE_OPENAI_API_KEY is a placeholder — set before applying secrets"
fi
if [[ "$PGPASSWORD" == "__PLACEHOLDER__" ]]; then
  warn "PGPASSWORD is a placeholder — set before applying secrets"
fi
