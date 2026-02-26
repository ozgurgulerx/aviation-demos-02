#!/usr/bin/env bash
# provision-azure.sh — Idempotent Azure resource provisioning for aviation-demos-02
# Usage: ./provision-azure.sh [--deploy-k8s] [--setup-github-oidc]
set -euo pipefail

###############################################################################
# Defaults — all overridable via environment
###############################################################################
APP_NAME="${APP_NAME:-aviation-multi-agent}"
LOCATION="${LOCATION:-westeurope}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-aviation-rag}"
VNET_NAME="${VNET_NAME:-vnet-aviation-rag}"
AKS_NAME="${AKS_NAME:-aks-aviation-rag}"
ACR_NAME="${ACR_NAME:-avrag705508acr}"
WEBAPP_NAME="${WEBAPP_NAME:-aviation-multiagent-frontend-705508}"
K8S_NAMESPACE="${K8S_NAMESPACE:-aviation-multi-agent}"
IMAGE_NAME="${IMAGE_NAME:-aviation-multi-agent-backend}"
AKS_VM_SIZE="${AKS_VM_SIZE:-Standard_D2als_v6}"

# Networking
VNET_CIDR="${VNET_CIDR:-10.2.0.0/16}"
SUBNET_AKS_CIDR="${SUBNET_AKS_CIDR:-10.2.0.0/22}"
SUBNET_APPSERVICE_CIDR="${SUBNET_APPSERVICE_CIDR:-10.2.4.0/24}"
SUBNET_PRIVATEENDPOINT_CIDR="${SUBNET_PRIVATEENDPOINT_CIDR:-10.2.5.0/24}"
AKS_SERVICE_CIDR="${AKS_SERVICE_CIDR:-10.3.0.0/16}"
AKS_DNS_IP="${AKS_DNS_IP:-10.3.0.10}"

# Tenant guardrails
TARGET_TENANT_ID="${TARGET_TENANT_ID:-52095a81-130f-4b06-83f1-9859b2c73de6}"
TARGET_SUBSCRIPTION_ID="${TARGET_SUBSCRIPTION_ID:-6a539906-6ce2-4e3b-84ee-89f701de18d8}"

# App Service plan
ASP_NAME="${ASP_NAME:-plan-aviation-rag-frontend}"
ASP_SKU="${ASP_SKU:-P1V3}"

# Flags
DEPLOY_K8S="${DEPLOY_K8S:-false}"
SETUP_GITHUB_OIDC="${SETUP_GITHUB_OIDC:-false}"
GITHUB_REPO="${GITHUB_REPO:-}"

# Parse CLI args
for arg in "$@"; do
  case $arg in
    --deploy-k8s) DEPLOY_K8S=true ;;
    --setup-github-oidc) SETUP_GITHUB_OIDC=true ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

###############################################################################
# Colors & logging
###############################################################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
info()    { echo -e "${BLUE}[i]${NC} $*"; }
err()     { echo -e "${RED}[✗]${NC} $*" >&2; }
die()     { err "$@"; exit 1; }
section() { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

###############################################################################
# Step 0: Tenant/subscription lock validation
###############################################################################
section "Step 0: Tenant & Subscription Validation"

if ! az account show &>/dev/null; then
  die "Azure CLI is not logged in. Run 'az login' first."
fi

CURRENT_TENANT=$(az account show --query tenantId -o tsv)
CURRENT_SUB=$(az account show --query id -o tsv)

if [[ "$CURRENT_TENANT" != "$TARGET_TENANT_ID" ]]; then
  die "TENANT MISMATCH — aborting to protect resources.
  Current:  $CURRENT_TENANT
  Expected: $TARGET_TENANT_ID"
fi

if [[ "$CURRENT_SUB" != "$TARGET_SUBSCRIPTION_ID" ]]; then
  die "SUBSCRIPTION MISMATCH — aborting to protect resources.
  Current:  $CURRENT_SUB
  Expected: $TARGET_SUBSCRIPTION_ID"
fi

log "Tenant:       $TARGET_TENANT_ID"
log "Subscription: $TARGET_SUBSCRIPTION_ID"

###############################################################################
# Step 1: Resource Group
###############################################################################
section "Step 1: Resource Group"

if az group show --name "$RESOURCE_GROUP" &>/dev/null; then
  log "Resource group '$RESOURCE_GROUP' already exists"
else
  info "Creating resource group '$RESOURCE_GROUP' in $LOCATION..."
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
  log "Created resource group '$RESOURCE_GROUP'"
fi

###############################################################################
# Step 2: Virtual Network + Subnets
###############################################################################
section "Step 2: Virtual Network & Subnets"

if az network vnet show --resource-group "$RESOURCE_GROUP" --name "$VNET_NAME" &>/dev/null 2>&1; then
  log "VNet '$VNET_NAME' already exists"
else
  info "Creating VNet '$VNET_NAME' ($VNET_CIDR)..."
  az network vnet create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VNET_NAME" \
    --address-prefix "$VNET_CIDR" \
    --output none
  log "Created VNet '$VNET_NAME'"
fi

# Subnet: AKS
if az network vnet subnet show --resource-group "$RESOURCE_GROUP" --vnet-name "$VNET_NAME" --name subnet-aks &>/dev/null 2>&1; then
  log "Subnet 'subnet-aks' already exists"
else
  info "Creating subnet 'subnet-aks' ($SUBNET_AKS_CIDR)..."
  az network vnet subnet create \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name subnet-aks \
    --address-prefixes "$SUBNET_AKS_CIDR" \
    --output none
  log "Created subnet 'subnet-aks'"
fi

# Subnet: App Service
if az network vnet subnet show --resource-group "$RESOURCE_GROUP" --vnet-name "$VNET_NAME" --name subnet-appservice &>/dev/null 2>&1; then
  log "Subnet 'subnet-appservice' already exists"
else
  info "Creating subnet 'subnet-appservice' ($SUBNET_APPSERVICE_CIDR)..."
  az network vnet subnet create \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name subnet-appservice \
    --address-prefixes "$SUBNET_APPSERVICE_CIDR" \
    --output none
  log "Created subnet 'subnet-appservice'"
fi

# Subnet: Private Endpoints
if az network vnet subnet show --resource-group "$RESOURCE_GROUP" --vnet-name "$VNET_NAME" --name subnet-privateendpoint &>/dev/null 2>&1; then
  log "Subnet 'subnet-privateendpoint' already exists"
else
  info "Creating subnet 'subnet-privateendpoint' ($SUBNET_PRIVATEENDPOINT_CIDR)..."
  az network vnet subnet create \
    --resource-group "$RESOURCE_GROUP" \
    --vnet-name "$VNET_NAME" \
    --name subnet-privateendpoint \
    --address-prefixes "$SUBNET_PRIVATEENDPOINT_CIDR" \
    --output none
  log "Created subnet 'subnet-privateendpoint'"
fi

###############################################################################
# Step 3: Validate reused ACR
###############################################################################
section "Step 3: Container Registry Validation"

if az acr show --name "$ACR_NAME" &>/dev/null 2>&1; then
  ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
  log "ACR '$ACR_NAME' exists: $ACR_LOGIN_SERVER"
else
  die "ACR '$ACR_NAME' not found. This is a reused resource and must exist."
fi

###############################################################################
# Step 4: AKS Cluster
###############################################################################
section "Step 4: AKS Cluster"

AKS_SUBNET_ID=$(az network vnet subnet show \
  --resource-group "$RESOURCE_GROUP" \
  --vnet-name "$VNET_NAME" \
  --name subnet-aks \
  --query id -o tsv)

if az aks show --resource-group "$RESOURCE_GROUP" --name "$AKS_NAME" &>/dev/null 2>&1; then
  log "AKS cluster '$AKS_NAME' already exists"

  # Ensure ACR is attached
  info "Ensuring ACR attachment..."
  az aks update \
    --resource-group "$RESOURCE_GROUP" \
    --name "$AKS_NAME" \
    --attach-acr "$ACR_NAME" \
    --output none 2>/dev/null || warn "ACR attach skipped (may already be attached or insufficient permissions)"
else
  info "Creating AKS cluster '$AKS_NAME' (VM: $AKS_VM_SIZE, nodes: 1-2)..."
  az aks create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$AKS_NAME" \
    --node-count 1 \
    --min-count 1 \
    --max-count 2 \
    --enable-cluster-autoscaler \
    --node-vm-size "$AKS_VM_SIZE" \
    --network-plugin azure \
    --vnet-subnet-id "$AKS_SUBNET_ID" \
    --service-cidr "$AKS_SERVICE_CIDR" \
    --dns-service-ip "$AKS_DNS_IP" \
    --generate-ssh-keys \
    --attach-acr "$ACR_NAME" \
    --enable-managed-identity \
    --output none
  log "Created AKS cluster '$AKS_NAME'"
fi

###############################################################################
# Step 5: App Service Plan + Web App
###############################################################################
section "Step 5: App Service (Frontend)"

# App Service Plan
if az appservice plan show --resource-group "$RESOURCE_GROUP" --name "$ASP_NAME" &>/dev/null 2>&1; then
  log "App Service plan '$ASP_NAME' already exists"
else
  info "Creating App Service plan '$ASP_NAME' ($ASP_SKU, Linux)..."
  az appservice plan create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ASP_NAME" \
    --sku "$ASP_SKU" \
    --is-linux \
    --output none
  log "Created App Service plan '$ASP_NAME'"
fi

# Web App
if az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" &>/dev/null 2>&1; then
  log "Web app '$WEBAPP_NAME' already exists"
else
  info "Creating web app '$WEBAPP_NAME'..."
  az webapp create \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$ASP_NAME" \
    --name "$WEBAPP_NAME" \
    --runtime "NODE:20-lts" \
    --output none
  log "Created web app '$WEBAPP_NAME'"
fi

###############################################################################
# Step 6: App Service VNet Integration + Settings
###############################################################################
section "Step 6: App Service Configuration"

info "Configuring VNet integration..."
az webapp vnet-integration add \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --vnet "$VNET_NAME" \
  --subnet subnet-appservice \
  --output none 2>/dev/null || warn "VNet integration may already be configured"

# App settings
info "Setting app configuration..."
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    PORT=3000 \
    WEBSITES_PORT=3000 \
    WEBSITE_VNET_ROUTE_ALL=1 \
  --output none

az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --startup-file "node server.js" \
  --output none

log "App Service configured"

###############################################################################
# Step 7: Managed Identity on App Service
###############################################################################
section "Step 7: Managed Identity"

IDENTITY_EXISTS=$(az webapp identity show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --query principalId -o tsv 2>/dev/null || echo "")

if [[ -n "$IDENTITY_EXISTS" ]]; then
  log "System-assigned managed identity already enabled: $IDENTITY_EXISTS"
else
  info "Enabling system-assigned managed identity..."
  PRINCIPAL_ID=$(az webapp identity assign \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --query principalId -o tsv)
  log "Managed identity enabled: $PRINCIPAL_ID"
fi

###############################################################################
# Step 8: Deploy K8s Manifests (optional)
###############################################################################
if [[ "$DEPLOY_K8S" == "true" ]]; then
  section "Step 8: Deploy Kubernetes Manifests"

  info "Getting AKS credentials..."
  az aks get-credentials \
    --resource-group "$RESOURCE_GROUP" \
    --name "$AKS_NAME" \
    --overwrite-existing

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  info "Rendering manifests..."
  export K8S_NAMESPACE IMAGE_NAME
  export AZURE_CONTAINER_REGISTRY="$ACR_LOGIN_SERVER"
  export IMAGE_TAG="${IMAGE_TAG:-latest}"
  bash "$SCRIPT_DIR/render-k8s-manifests.sh"

  RENDERED_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)/k8s/rendered"

  info "Applying manifests in order..."
  kubectl apply -f "$RENDERED_DIR/namespace.yaml"
  kubectl apply -f "$RENDERED_DIR/backend-serviceaccount.yaml"
  kubectl apply -f "$RENDERED_DIR/backend-service.yaml"
  # backend-secret.yaml is skipped — create secrets via kubectl:
  #   kubectl create secret generic backend-secrets --namespace=<ns> \
  #     --from-literal=AZURE_OPENAI_API_KEY=<key> \
  #     --from-literal=PGPASSWORD=<pw> \
  #     --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f "$RENDERED_DIR/backend-configmap.yaml"
  kubectl apply -f "$RENDERED_DIR/redis-deployment.yaml"
  kubectl apply -f "$RENDERED_DIR/backend-deployment.yaml"
  kubectl apply -f "$RENDERED_DIR/backend-hpa.yaml"
  kubectl apply -f "$RENDERED_DIR/backend-networkpolicy.yaml"
  kubectl apply -f "$RENDERED_DIR/backend-pdb.yaml"
  kubectl apply -f "$RENDERED_DIR/ingress.yaml" 2>/dev/null || warn "Ingress apply skipped (ingress controller may not be installed)"

  log "Kubernetes manifests applied"
fi

###############################################################################
# Step 9: GitHub OIDC (optional)
###############################################################################
if [[ "$SETUP_GITHUB_OIDC" == "true" ]]; then
  section "Step 9: GitHub OIDC Configuration"

  if [[ -z "$GITHUB_REPO" ]]; then
    die "GITHUB_REPO must be set (e.g., 'owner/repo') for OIDC setup"
  fi

  OIDC_APP_NAME="${APP_NAME}-github-oidc"

  # Check if app registration exists
  EXISTING_APP=$(az ad app list --display-name "$OIDC_APP_NAME" --query "[0].appId" -o tsv 2>/dev/null || echo "")

  if [[ -n "$EXISTING_APP" ]]; then
    log "App registration '$OIDC_APP_NAME' already exists: $EXISTING_APP"
    APP_ID="$EXISTING_APP"
  else
    info "Creating app registration '$OIDC_APP_NAME'..."
    APP_ID=$(az ad app create --display-name "$OIDC_APP_NAME" --query appId -o tsv)
    log "Created app registration: $APP_ID"

    # Create service principal
    az ad sp create --id "$APP_ID" --output none
    log "Created service principal"
  fi

  # Add federated credential for main branch
  CRED_NAME="github-main"
  EXISTING_CRED=$(az ad app federated-credential list --id "$APP_ID" \
    --query "[?name=='$CRED_NAME'].name" -o tsv 2>/dev/null || echo "")

  if [[ -n "$EXISTING_CRED" ]]; then
    log "Federated credential '$CRED_NAME' already exists"
  else
    info "Adding federated credential for $GITHUB_REPO (main branch)..."
    az ad app federated-credential create --id "$APP_ID" --parameters "{
      \"name\": \"$CRED_NAME\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"repo:${GITHUB_REPO}:ref:refs/heads/main\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }" --output none
    log "Added federated credential"
  fi

  # Assign Contributor on resource group
  SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
  info "Assigning Contributor role on $RESOURCE_GROUP..."
  az role assignment create \
    --assignee "$SP_ID" \
    --role Contributor \
    --scope "/subscriptions/$TARGET_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
    --output none 2>/dev/null || warn "Role assignment may already exist"

  # Assign AcrPush on ACR
  ACR_ID=$(az acr show --name "$ACR_NAME" --query id -o tsv)
  az role assignment create \
    --assignee "$SP_ID" \
    --role AcrPush \
    --scope "$ACR_ID" \
    --output none 2>/dev/null || warn "ACR role assignment may already exist"

  echo ""
  log "GitHub OIDC configured. Set these GitHub secrets:"
  echo "  AZURE_CLIENT_ID = $APP_ID"
  echo "  AZURE_TENANT_ID = $TARGET_TENANT_ID"
  echo "  AZURE_SUBSCRIPTION_ID = $TARGET_SUBSCRIPTION_ID"
fi

###############################################################################
# Summary
###############################################################################
section "Provisioning Complete"
echo ""
echo "  Resource Group:  $RESOURCE_GROUP"
echo "  VNet:            $VNET_NAME ($VNET_CIDR)"
echo "  AKS:             $AKS_NAME ($AKS_VM_SIZE)"
echo "  ACR:             $ACR_LOGIN_SERVER"
echo "  Web App:         $WEBAPP_NAME"
echo "  Namespace:       $K8S_NAMESPACE"
echo ""
log "All resources provisioned successfully"
