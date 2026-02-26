#!/usr/bin/env bash
# use-deploy-target-context.sh — Sets kubectl context to deploy target AKS
set -euo pipefail

###############################################################################
# Defaults (override via environment)
###############################################################################
TARGET_TENANT_ID="${TARGET_TENANT_ID:-52095a81-130f-4b06-83f1-9859b2c73de6}"
TARGET_SUBSCRIPTION_ID="${TARGET_SUBSCRIPTION_ID:-6a539906-6ce2-4e3b-84ee-89f701de18d8}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-aviation-rag}"
AKS_NAME="${AKS_NAME:-aks-aviation-rag}"

###############################################################################
# Colors
###############################################################################
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
die()  { err "$@"; exit 1; }

###############################################################################
# 1. Validate tenant/subscription
###############################################################################
echo "=== Setting kubectl context to deploy target ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/validate-tenant-lock.sh" 2>/dev/null || {
  # Inline validation if source fails
  CURRENT_TENANT=$(az account show --query tenantId -o tsv)
  CURRENT_SUB=$(az account show --query id -o tsv)
  [[ "$CURRENT_TENANT" == "$TARGET_TENANT_ID" ]] || die "Tenant mismatch!"
  [[ "$CURRENT_SUB" == "$TARGET_SUBSCRIPTION_ID" ]] || die "Subscription mismatch!"
}

###############################################################################
# 2. Get AKS credentials
###############################################################################
echo ""
echo "Fetching AKS credentials..."
az aks get-credentials \
  --resource-group "$RESOURCE_GROUP" \
  --name "$AKS_NAME" \
  --overwrite-existing

###############################################################################
# 3. Verify context
###############################################################################
CURRENT_CTX=$(kubectl config current-context)
log "kubectl context set to: $CURRENT_CTX"

# Quick cluster connectivity check
if kubectl cluster-info &>/dev/null; then
  log "Cluster is reachable"
else
  err "Cluster is not reachable. Check VPN or network connectivity."
  exit 1
fi

echo ""
log "Ready to deploy to $AKS_NAME"
