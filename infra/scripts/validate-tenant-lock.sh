#!/usr/bin/env bash
# validate-tenant-lock.sh — Validates Azure CLI context and tenant guardrails
set -euo pipefail

###############################################################################
# Defaults (override via environment)
###############################################################################
TARGET_TENANT_ID="${TARGET_TENANT_ID:-52095a81-130f-4b06-83f1-9859b2c73de6}"
TARGET_SUBSCRIPTION_ID="${TARGET_SUBSCRIPTION_ID:-6a539906-6ce2-4e3b-84ee-89f701de18d8}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-aviation-rag}"
AKS_NAME="${AKS_NAME:-aks-aviation-rag}"
K8S_NAMESPACE="${K8S_NAMESPACE:-aviation-multi-agent}"

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
# 1. Azure CLI logged in?
###############################################################################
echo "=== Tenant & Subscription Lock Validation ==="

if ! az account show &>/dev/null; then
  die "Azure CLI is not logged in. Run 'az login' first."
fi

###############################################################################
# 2. Tenant match
###############################################################################
CURRENT_TENANT=$(az account show --query tenantId -o tsv)
if [[ "$CURRENT_TENANT" != "$TARGET_TENANT_ID" ]]; then
  die "Tenant mismatch! Current: $CURRENT_TENANT  Expected: $TARGET_TENANT_ID"
fi
log "Tenant ID matches: $TARGET_TENANT_ID"

###############################################################################
# 3. Subscription match
###############################################################################
CURRENT_SUB=$(az account show --query id -o tsv)
if [[ "$CURRENT_SUB" != "$TARGET_SUBSCRIPTION_ID" ]]; then
  die "Subscription mismatch! Current: $CURRENT_SUB  Expected: $TARGET_SUBSCRIPTION_ID"
fi
log "Subscription ID matches: $TARGET_SUBSCRIPTION_ID"

###############################################################################
# 4. Resource group exists?
###############################################################################
if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
  log "Resource group '$RESOURCE_GROUP' exists"
else
  warn "Resource group '$RESOURCE_GROUP' does not exist yet"
fi

###############################################################################
# 5. AKS cluster exists?
###############################################################################
if az aks show --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" &>/dev/null 2>&1; then
  log "AKS cluster '$AKS_NAME' exists in '$RESOURCE_GROUP'"

  # Check power state
  POWER_STATE=$(az aks show --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" \
    --query "powerState.code" -o tsv 2>/dev/null || echo "Unknown")
  if [[ "$POWER_STATE" == "Running" ]]; then
    log "AKS power state: Running"
  else
    warn "AKS power state: $POWER_STATE"
  fi
else
  warn "AKS cluster '$AKS_NAME' does not exist yet in '$RESOURCE_GROUP'"
fi

###############################################################################
# 6. Kubernetes context validation (if kubectl available)
###############################################################################
if command -v kubectl &>/dev/null; then
  CURRENT_CTX=$(kubectl config current-context 2>/dev/null || echo "none")
  if [[ "$CURRENT_CTX" == *"$AKS_NAME"* ]]; then
    log "kubectl context matches AKS cluster: $CURRENT_CTX"

    # Check namespace configmap guardrails
    if kubectl get configmap backend-config -n "$K8S_NAMESPACE" &>/dev/null 2>&1; then
      RUNTIME_TENANT=$(kubectl get configmap backend-config -n "$K8S_NAMESPACE" \
        -o jsonpath='{.data.EXPECTED_RUNTIME_TENANT_ID}' 2>/dev/null || echo "")
      if [[ -n "$RUNTIME_TENANT" && "$RUNTIME_TENANT" != "$TARGET_TENANT_ID" ]]; then
        die "ConfigMap tenant guardrail mismatch! ConfigMap: $RUNTIME_TENANT  Expected: $TARGET_TENANT_ID"
      elif [[ -n "$RUNTIME_TENANT" ]]; then
        log "ConfigMap tenant guardrail matches"
      else
        warn "ConfigMap does not have EXPECTED_RUNTIME_TENANT_ID set"
      fi
    else
      warn "ConfigMap 'backend-config' not found in namespace '$K8S_NAMESPACE'"
    fi
  else
    warn "kubectl context '$CURRENT_CTX' does not match AKS cluster '$AKS_NAME'"
  fi
else
  warn "kubectl not found; skipping Kubernetes context validation"
fi

echo ""
log "All validations passed."
