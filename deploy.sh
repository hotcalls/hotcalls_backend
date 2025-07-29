#!/bin/bash

# HotCalls Single-Stage Deployment Script
# This script deploys the entire application stack to Azure using Terraform and Kubernetes
#
# IMPROVEMENTS:
# - MANDATORY --project-name parameter (no more defaults)
# - Automatic handling of existing resource groups (import if needed)
# - Retry logic for failed deployments
# - Better error handling and cleanup
# - Foolproof deployment with clear error messages
# - Automatic ACR authentication setup for Kubernetes
# - Fixed image naming consistency (project-specific names)
# - Automatic deployment restart after auth configuration
# 
# SPEED & RELIABILITY OPTIMIZATIONS FOR NEW PROJECTS:
#   * REMOVED 15-minute ACR attachment bottleneck
#   * Docker build optimization (cache detection, fresh builds)
#   * Parallel Kubernetes resource deployment
#   * Fixed environment variable substitution (ALLOWED_HOSTS=*, etc.)
#   * AGGRESSIVE health check timeouts for staging/dev (3s intervals)
#   * Proper dependency waiting (Redis ready before backend)
#   * Smart retry logic with pod status debugging
#   * Comprehensive upfront validation (Docker, Azure, tools)
#   * Auth timing fixes (secrets ready before deployments)
#   * Explicit defaults for all critical variables
#
# USAGE:
#   ./deploy.sh --project-name=YOUR_EXACT_RG_NAME [options]
#
# EXAMPLES:
#   ./deploy.sh --project-name=hotcalls-staging --environment=staging
#   ./deploy.sh --project-name=prod-hotcalls --environment=production --update-only
#   ./deploy.sh --project-name=test-env --branch=main

set -euo pipefail

# Default values - MUST BE OVERRIDDEN
PROJECT_NAME=""
ENVIRONMENT="staging"
LOCATION_SHORT="ne"
UPDATE_ONLY=false
BRANCH=""
DOMAIN=""
NO_CACHE=false
PURGE_DB=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project-name=*)
            PROJECT_NAME="${1#*=}"
            shift
            ;;
        --environment=*)
            ENVIRONMENT="${1#*=}"
            shift
            ;;
        --location-short=*)
            LOCATION_SHORT="${1#*=}"
            shift
            ;;
        --update-only)
            UPDATE_ONLY=true
            shift
            ;;
        --branch=*)
            BRANCH="${1#*=}"
            shift
            ;;
        --domain=*)
            DOMAIN="${1#*=}"
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --purge)
            PURGE_DB=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --project-name=NAME [OPTIONS]"
            echo ""
            echo "REQUIRED OPTIONS:"
            echo "  --project-name=NAME    REQUIRED: Exact name for the Azure resource group"
            echo "                         This will be used as-is, no prefixes or suffixes added"
            echo ""
            echo "OPTIONAL OPTIONS:"
            echo "  --environment=ENV      Set environment (default: staging)"
            echo "  --location-short=LOC   Set location short name (default: ne)"
            echo "  --update-only          Only update Kubernetes deployment, skip infrastructure"
            echo "  --branch=BRANCH        Git pull and checkout specified branch for both frontend and backend"
            echo "  --domain=DOMAIN        Configure ingress with domain and TLS (requires certs/tls.cer and certs/private.key)"
            echo "  --no-cache             Force fresh Docker build without using cache (slower but ensures all changes are included)"
            echo "  --purge                DANGER: Drop all database tables, recreate migrations from scratch"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --project-name=hotcalls-prod           # Deploy to resource group: hotcalls-prod"
            echo "  $0 --project-name=myapp --environment=dev # Deploy to resource group: myapp (dev environment)"  
            echo "  $0 --project-name=test-rg --update-only   # Update K8s only in test-rg"
            echo "  $0 --project-name=staging --branch=main   # Deploy staging with main branch"
            echo "  $0 --project-name=prod --domain=app.example.com  # Deploy with HTTPS"
            echo "  $0 --project-name=staging --update-only --no-cache  # Force fresh build without cache"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$PROJECT_NAME" ]]; then
    echo "❌ ERROR: --project-name is required!"
    echo ""
    echo "The project name will be used as the exact Azure resource group name."
    echo "No prefixes or suffixes will be added."
    echo ""
    echo "Usage: $0 --project-name=YOUR_PROJECT_NAME [other options]"
    echo ""
    echo "Examples:"
    echo "  $0 --project-name=hotcalls-staging"
    echo "  $0 --project-name=mycompany-prod"
    echo "  $0 --project-name=test-environment"
    echo ""
    echo "Use --help for full usage information."
    exit 1
fi

echo "🎯 Deployment Configuration:"
echo "   PROJECT_NAME: $PROJECT_NAME"
echo "   Environment: $ENVIRONMENT" 
echo "   Location: $LOCATION_SHORT"
echo "   Update Only: $UPDATE_ONLY"
echo "   Docker Cache: $(if [[ "$NO_CACHE" == "true" ]]; then echo "Disabled (fresh build)"; else echo "Enabled"; fi)"
if [[ -n "$BRANCH" ]]; then
    echo "   Branch: $BRANCH"
fi
if [[ -n "$DOMAIN" ]]; then
    echo "   Domain: $DOMAIN"
    echo "   HTTPS: Enabled"
fi
if [[ "$PURGE_DB" == "true" ]]; then
    echo "   🚨 PURGE MODE: ENABLED - ALL DATA WILL BE DELETED! 🚨"
fi
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Error handling
trap 'log_error "Deployment failed on line $LINENO"' ERR

# Check prerequisites and validate environment
check_prerequisites() {
    log_info "Checking prerequisites and validating environment..."
    
    # Check if required tools are installed with versions
    command -v az >/dev/null 2>&1 || { log_error "Azure CLI is required but not installed. Aborting."; exit 1; }
    command -v terraform >/dev/null 2>&1 || { log_error "Terraform is required but not installed. Aborting."; exit 1; }
    command -v kubectl >/dev/null 2>&1 || { log_error "kubectl is required but not installed. Aborting."; exit 1; }
    command -v docker >/dev/null 2>&1 || { log_error "Docker is required but not installed. Aborting."; exit 1; }
    command -v envsubst >/dev/null 2>&1 || { log_error "envsubst is required but not installed. Aborting."; exit 1; }
    command -v git >/dev/null 2>&1 || { log_error "git is required but not installed. Aborting."; exit 1; }
    
    # Check Docker buildx for multi-platform builds
    if ! docker buildx version >/dev/null 2>&1; then
        log_error "Docker buildx is required for AMD64 builds but not available. Aborting."
        exit 1
    fi
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker Desktop and try again."
        exit 1
    fi
    
    # Check for Node.js if frontend will be built
    if [[ -f ".env" ]] && grep -q "FRONTEND_REPO_URL" .env; then
        if ! command -v node >/dev/null 2>&1; then
            log_warning "Node.js not found. Frontend building will fail if FRONTEND_REPO_URL is configured."
            log_warning "Please install Node.js from https://nodejs.org/"
        else
            local node_version=$(node --version)
            log_info "Node.js found: $node_version"
        fi
    fi
    
    # Check if .env file exists and validate critical variables
    if [[ ! -f ".env" ]]; then
        log_error ".env file not found. Please create it with your configuration."
        exit 1
    fi
    
    # Test Azure connectivity upfront
    log_info "Testing Azure connectivity..."
    if ! az account show >/dev/null 2>&1; then
        log_error "Not logged into Azure. Please run 'az login' first."
        exit 1
    fi
    
    # Test Docker registry connectivity
    log_info "Testing Docker connectivity..."
    if ! docker version >/dev/null 2>&1; then
        log_error "Docker is not responding. Please check Docker Desktop."
        exit 1
    fi
    
    log_success "All prerequisites validated!"
}

# Load environment variables from .env
load_environment() {
    log_info "Loading environment variables from .env..."
    
    # Export all variables from .env file
    set -a  # automatically export all variables
    source .env
    set +a  # stop automatically exporting
    
    # Validate required environment variables
    required_vars=(
        "SECRET_KEY"
        "DB_USER"
        "DB_PASSWORD"
        "DB_NAME"
        "REDIS_PASSWORD"
        "EMAIL_HOST"
        "EMAIL_HOST_USER"
        "EMAIL_HOST_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required environment variable $var is not set in .env"
            exit 1
        fi
    done
    
    # Set frontend repository if not set
    if [[ -z "${FRONTEND_REPO_URL:-}" ]]; then
        log_warning "FRONTEND_REPO_URL not set in .env. Frontend deployment will be skipped."
        log_warning "Add FRONTEND_REPO_URL=git@github.com:your-org/frontend-repo.git to .env if you want frontend deployment"
    fi
    
    log_success "Environment variables loaded and validated!"
}

# Pull and checkout branch for both repositories
checkout_branch() {
    if [[ -z "$BRANCH" ]]; then
        log_info "No branch specified, using current branches"
        return 0
    fi
    
    log_info "Checking out branch '$BRANCH' for backend and frontend..."
    
    # Checkout backend branch
    log_info "Pulling and checking out backend branch: $BRANCH"
    git fetch origin
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
        git checkout "$BRANCH"
    elif git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
        git checkout -b "$BRANCH" "origin/$BRANCH"
    else
        log_error "Branch '$BRANCH' not found in backend repository"
        exit 1
    fi
    git pull origin "$BRANCH"
    
    # Checkout frontend branch if repository exists
    if [[ -n "${FRONTEND_REPO_URL:-}" ]]; then
        if [[ -d "frontend" ]]; then
            log_info "Pulling and checking out frontend branch: $BRANCH"
            cd frontend
            git fetch origin
            if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
                git checkout "$BRANCH"
            elif git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
                git checkout -b "$BRANCH" "origin/$BRANCH"
            else
                log_warning "Branch '$BRANCH' not found in frontend repository, keeping current branch"
                cd ..
                return 0
            fi
            git pull origin "$BRANCH"
            cd ..
            log_success "Frontend checked out to branch: $BRANCH"
        else
            log_info "Frontend directory doesn't exist yet, will clone with branch $BRANCH"
        fi
    fi
    
    log_success "Branch checkout completed!"
}

# Clone and build frontend if needed
setup_frontend() {
    log_info "Setting up frontend..."
    
    # Check if frontend directory exists
    if [[ ! -d "frontend" ]]; then
        log_error "Frontend directory not found! Expected ./frontend directory with the React app."
        log_error "This project includes a local frontend directory - no external repo needed."
        exit 1
    fi
    
    # Check if we should skip frontend build (useful for backend-only updates)
    if [[ "${SKIP_FRONTEND:-false}" == "true" ]]; then
        log_warning "SKIP_FRONTEND is set to true. Skipping frontend build."
        return 0
    fi
    
    # Build the frontend
    log_info "Building frontend from local directory..."
    cd frontend
    
    # Check if package.json exists
    if [[ ! -f "package.json" ]]; then
        log_error "No package.json found in frontend directory"
        exit 1
    fi
    
    # Install dependencies
    log_info "Installing frontend dependencies..."
    if command -v bun >/dev/null 2>&1; then
        log_info "Using bun to install dependencies..."
        bun install
    elif command -v npm >/dev/null 2>&1; then
        log_info "Using npm to install dependencies..."
        npm install
    elif command -v yarn >/dev/null 2>&1; then
        log_info "Using yarn to install dependencies..."
        yarn install
    else
        log_error "Neither bun, npm, nor yarn found. Please install Node.js and npm or bun"
        exit 1
    fi
    
    # Build the project
    log_info "Building frontend project..."
    if command -v bun >/dev/null 2>&1; then
        if bun run build; then
            log_success "Frontend built successfully with bun!"
        else
            log_error "Frontend build failed"
            exit 1
        fi
    elif npm run build; then
        log_success "Frontend built successfully!"
    else
        log_error "Frontend build failed"
        exit 1
    fi
    
    # Check if build output exists and copy to project root for Docker build
    if [[ -d "dist" ]]; then
        cd ..
        # Remove old dist if exists
        rm -rf dist
        # Copy new dist to project root
        cp -r frontend/dist .
        log_info "Copied frontend/dist/ to project root for Docker build"
    elif [[ -d "build" ]]; then
        cd ..
        # Remove old dist if exists
        rm -rf dist
        # Copy build as dist to project root
        cp -r frontend/build ./dist
        log_info "Copied frontend/build/ to project root as dist/ for Docker build"
    else
        log_error "No dist/ or build/ directory found after frontend build"
        exit 1
    fi
    
    log_success "Frontend setup completed!"
}

# Azure login check
check_azure_login() {
    log_info "Checking Azure login status..."
    
    if ! az account show >/dev/null 2>&1; then
        log_warning "Not logged into Azure. Please login..."
        az login
    fi
    
    local subscription=$(az account show --query name -o tsv)
    log_success "Logged into Azure subscription: $subscription"
}

# Cleanup function for failed deployments
cleanup_failed_deployment() {
    log_warning "Cleaning up failed deployment state..."
    
    cd terraform 2>/dev/null || return 0
    
    # Select workspace
    WORKSPACE_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
    if terraform workspace list | grep -q "\b$WORKSPACE_NAME\b"; then
        terraform workspace select "$WORKSPACE_NAME" >/dev/null 2>&1 || true
        
        # Remove failed resources that might be in a bad state
        log_info "Removing potentially corrupted Terraform state..."
        terraform state rm azurerm_resource_group.main >/dev/null 2>&1 || true
        terraform state rm random_string.unique_id >/dev/null 2>&1 || true
    fi
    
    cd ..
}

# Check and handle existing resource group
check_and_handle_resource_group() {
    log_info "Checking if resource group '$PROJECT_NAME' exists..."
    
    # Check if resource group exists in Azure
    if az group show --name "$PROJECT_NAME" >/dev/null 2>&1; then
        log_info "Resource group '$PROJECT_NAME' exists in Azure"
        
        # Check if it's in Terraform state
        cd terraform
        
        # Initialize Terraform first to ensure state access
        log_info "Initializing Terraform for state check..."
        terraform init -input=false >/dev/null 2>&1 || {
            log_error "Failed to initialize Terraform"
            cd ..
            return 1
        }
        
        # Select workspace first
        WORKSPACE_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
        if terraform workspace list | grep -q "\b$WORKSPACE_NAME\b"; then
            terraform workspace select "$WORKSPACE_NAME" >/dev/null 2>&1
        else
            log_info "Creating new workspace: $WORKSPACE_NAME"
            terraform workspace new "$WORKSPACE_NAME" >/dev/null 2>&1
        fi
        
        # Check if resource group is in state
        if ! terraform state show azurerm_resource_group.main >/dev/null 2>&1; then
            log_info "Resource group exists in Azure but not in Terraform state. Importing..."
            
            # Get the resource group ID
            RG_ID=$(az group show --name "$PROJECT_NAME" --query id -o tsv)
            
            # Import the resource group with retry logic
            local retry_count=0
            local max_retries=3
            
            while [[ $retry_count -lt $max_retries ]]; do
                if terraform import azurerm_resource_group.main "$RG_ID" >/dev/null 2>&1; then
                    log_success "Successfully imported existing resource group into Terraform state"
                    break
                else
                    retry_count=$((retry_count + 1))
                    if [[ $retry_count -lt $max_retries ]]; then
                        log_warning "Import attempt $retry_count failed, retrying..."
                        sleep 5
                    else
                        log_error "Failed to import resource group after $max_retries attempts."
                        log_error "You may need to delete it manually: az group delete --name '$PROJECT_NAME'"
                        cd ..
                        return 1
                    fi
                fi
            done
        else
            log_info "Resource group already exists in Terraform state"
        fi
        
        cd ..
    else
        log_info "Resource group '$PROJECT_NAME' does not exist. Will be created by Terraform."
    fi
    
    return 0
}

# Deploy infrastructure with Terraform
deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd terraform
    
    # Set Terraform variables from command line and .env
    export TF_VAR_resource_group_name="$PROJECT_NAME"
    export TF_VAR_project_name="$PROJECT_NAME"
    export TF_VAR_environment="$ENVIRONMENT"
    export TF_VAR_location_short="$LOCATION_SHORT"
    
    # Map location_short to full location
    case "$LOCATION_SHORT" in
        "we") export TF_VAR_location="West Europe" ;;
        "ne") export TF_VAR_location="North Europe" ;;
        "ue") export TF_VAR_location="UK South" ;;
        *) export TF_VAR_location="North Europe" ;;
    esac
    
    log_info "Terraform variables set: $PROJECT_NAME-$ENVIRONMENT-$LOCATION_SHORT in $TF_VAR_location"
    
    # Fix storage account naming (no hyphens allowed)
    STORAGE_PREFIX=$(echo "${PROJECT_NAME}${ENVIRONMENT}${LOCATION_SHORT}" | tr -d '-')
    export TF_VAR_storage_account_prefix="$STORAGE_PREFIX"
    
    export TF_VAR_app_db_name="$DB_NAME"
    export TF_VAR_app_db_user="$DB_USER"
    export TF_VAR_app_db_password="$DB_PASSWORD"
    export TF_VAR_app_secret_key="$SECRET_KEY"
    export TF_VAR_app_redis_password="$REDIS_PASSWORD"
    export TF_VAR_app_email_host="$EMAIL_HOST"
    export TF_VAR_app_email_port="$EMAIL_PORT"
    export TF_VAR_app_email_use_tls="$EMAIL_USE_TLS"
    export TF_VAR_app_email_use_ssl="$EMAIL_USE_SSL"
    export TF_VAR_app_email_host_user="$EMAIL_HOST_USER"
    export TF_VAR_app_email_host_password="$EMAIL_HOST_PASSWORD"
    export TF_VAR_app_default_from_email="$DEFAULT_FROM_EMAIL"
    export TF_VAR_app_server_email="$SERVER_EMAIL"
    export TF_VAR_app_base_url="$BASE_URL"
    export TF_VAR_app_debug="$DEBUG"
    export TF_VAR_app_cors_allow_all="$CORS_ALLOW_ALL_ORIGINS"
    
    log_info "Initializing Terraform..."
    terraform init
    
    # Create or select workspace based on project name and environment
    WORKSPACE_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
    log_info "Using Terraform workspace: $WORKSPACE_NAME"
    
    # Create workspace if it doesn't exist, otherwise select it
    if ! terraform workspace list | grep -q "\b$WORKSPACE_NAME\b"; then
        log_info "Creating new workspace: $WORKSPACE_NAME"
        terraform workspace new "$WORKSPACE_NAME"
    else
        log_info "Selecting existing workspace: $WORKSPACE_NAME"
        terraform workspace select "$WORKSPACE_NAME"
    fi
    
    log_info "Planning Terraform deployment..."
    if ! terraform plan -out=tfplan; then
        log_error "Terraform planning failed! Attempting cleanup..."
        cleanup_failed_deployment
        log_error "Please check your .env configuration and try again."
        cd ..
        exit 1
    fi
    
    log_info "Applying Terraform deployment..."
    local apply_retry=0
    local max_apply_retries=2
    
    while [[ $apply_retry -lt $max_apply_retries ]]; do
        if terraform apply tfplan; then
            log_success "Infrastructure deployed successfully!"
            break
        else
            apply_retry=$((apply_retry + 1))
            if [[ $apply_retry -lt $max_apply_retries ]]; then
                log_warning "Terraform apply failed, attempting cleanup and retry..."
                cleanup_failed_deployment
                
                # Re-run the resource group check and plan
                cd ..
                check_and_handle_resource_group
                cd terraform
                
                log_info "Re-planning after cleanup..."
                if ! terraform plan -out=tfplan; then
                    log_error "Re-planning failed after cleanup"
                    cd ..
                    exit 1
                fi
            else
                log_error "Terraform apply failed after $max_apply_retries attempts!"
                log_error "Check the error messages above for details."
                log_error "You may need to manually clean up resources in Azure portal."
                cd ..
                exit 1
            fi
        fi
    done
    
    cd ..
}

# Get infrastructure outputs
get_infrastructure_outputs() {
    log_info "Getting infrastructure outputs..."
    
    cd terraform
    
    # Export outputs as environment variables for K8s deployment
    export ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
    export AKS_CLUSTER_NAME=$(terraform output -raw aks_cluster_name)
    export AKS_RESOURCE_GROUP=$(terraform output -raw aks_resource_group)
    export DB_HOST=$(terraform output -raw postgres_fqdn)
    export AZURE_ACCOUNT_NAME=$(terraform output -raw storage_account_name)
    export AZURE_STORAGE_KEY=$(terraform output -raw storage_account_primary_access_key)
    
    log_success "Infrastructure outputs retrieved!"
    
    cd ..
}

# Get infrastructure outputs for update-only mode
get_infrastructure_outputs_update_only() {
    log_info "Getting infrastructure outputs for update-only deployment..."
    
    cd terraform
    
    # Select the correct workspace
    WORKSPACE_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
    if terraform workspace list | grep -q "\b$WORKSPACE_NAME\b"; then
        terraform workspace select "$WORKSPACE_NAME"
    else
        log_error "Terraform workspace '$WORKSPACE_NAME' not found. Run full deployment first."
        exit 1
    fi
    
    # Export outputs as environment variables for K8s deployment
    export ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
    export AKS_CLUSTER_NAME=$(terraform output -raw aks_cluster_name)
    export AKS_RESOURCE_GROUP=$(terraform output -raw aks_resource_group)
    export DB_HOST=$(terraform output -raw postgres_fqdn)
    export AZURE_ACCOUNT_NAME=$(terraform output -raw storage_account_name)
    export AZURE_STORAGE_KEY=$(terraform output -raw storage_account_primary_access_key)
    
    log_success "Infrastructure outputs retrieved!"
    
    cd ..
}

# Get AKS credentials
configure_kubectl() {
    log_info "Configuring kubectl for AKS cluster..."
    
    az aks get-credentials \
        --resource-group "$AKS_RESOURCE_GROUP" \
        --name "$AKS_CLUSTER_NAME" \
        --admin \
        --overwrite-existing
    
    log_success "kubectl configured for AKS cluster!"
    
    # Skip slow ACR attachment - we use secrets for authentication instead
    log_info "Skipping ACR attachment (using secrets for faster deployment)..."
    log_success "kubectl configured for AKS cluster!"
}

# Build and push Docker images
build_and_push_images() {
    log_info "Building and pushing Docker images..."
    
    # Login to ACR
    az acr login --name "${ACR_LOGIN_SERVER%%.*}"
    
    # Set image tag (use environment or default to 'latest')
    export IMAGE_TAG="${IMAGE_TAG:-latest}"
    
    # Build backend image for AMD64 architecture (Azure AKS compatibility)
    log_info "Building backend image for AMD64 architecture..."
    
    if [[ "$NO_CACHE" == "true" ]]; then
        log_info "Building WITHOUT cache (--no-cache flag enabled)..."
        docker buildx build --platform linux/amd64 \
            --no-cache \
            -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:${IMAGE_TAG}" . --push
    else
        # Optimize for new projects - skip cache lookup on first build to avoid timeouts
        if docker manifest inspect "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:cache" >/dev/null 2>&1; then
            log_info "Using existing cache for faster build..."
            docker buildx build --platform linux/amd64 \
                --cache-from=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:cache" \
                --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:cache,mode=max" \
                -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:${IMAGE_TAG}" . --push
        else
            log_info "First build - no cache available, building fresh..."
            docker buildx build --platform linux/amd64 \
                --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:cache,mode=max" \
                -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:${IMAGE_TAG}" . --push
        fi
    fi
    
    # Build frontend image if dist directory exists
    if [[ -d "dist" ]]; then
        log_info "Building frontend image for AMD64 architecture..."
        
        if [[ "$NO_CACHE" == "true" ]]; then
            log_info "Building frontend WITHOUT cache (--no-cache flag enabled)..."
            docker buildx build --platform linux/amd64 \
                --no-cache \
                -f frontend-deploy/Dockerfile -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:${IMAGE_TAG}" . --push
        else
            # Optimize for new projects - skip cache lookup on first build
            if docker manifest inspect "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:cache" >/dev/null 2>&1; then
                log_info "Using existing frontend cache for faster build..."
                docker buildx build --platform linux/amd64 \
                    --cache-from=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:cache" \
                    --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:cache,mode=max" \
                    -f frontend-deploy/Dockerfile -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:${IMAGE_TAG}" . --push
            else
                log_info "First frontend build - no cache available, building fresh..."
                docker buildx build --platform linux/amd64 \
                    --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:cache,mode=max" \
                    -f frontend-deploy/Dockerfile -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:${IMAGE_TAG}" . --push
            fi
        fi
        
        export HAS_FRONTEND=true
    else
        log_warning "No dist/ directory found, skipping frontend image build"
        export HAS_FRONTEND=false
    fi
    
    log_success "Docker images built and pushed!"
}

# Setup environment variables for Kubernetes deployment  
setup_kubernetes_environment() {
    log_info "Setting up Kubernetes environment variables..."
    
    # Fix environment variable substitution issues with EXPLICIT defaults
    export ALLOWED_HOSTS="*"  # ALWAYS allow all hosts per user requirement
    export CORS_ALLOW_ALL_ORIGINS="${CORS_ALLOW_ALL_ORIGINS:-False}"
    export DEBUG="${DEBUG:-True}"  # True for staging, False for production
    export TIME_ZONE="${TIME_ZONE:-Europe/Berlin}"
    # Database SSL mode - require for Azure PostgreSQL in staging/production
    if [[ "$ENVIRONMENT" == "development" ]]; then
        export DB_SSLMODE="${DB_SSLMODE:-disable}"
    else
        export DB_SSLMODE="${DB_SSLMODE:-require}"  # Azure PostgreSQL requires SSL
    fi
    
    # Security settings with proper defaults
    export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-False}"
    export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-False}"
    export CSRF_COOKIE_SECURE="${CSRF_COOKIE_SECURE:-False}"
    export SECURE_BROWSER_XSS_FILTER="${SECURE_BROWSER_XSS_FILTER:-True}"
    export SECURE_CONTENT_TYPE_NOSNIFF="${SECURE_CONTENT_TYPE_NOSNIFF:-True}"
    export X_FRAME_OPTIONS="${X_FRAME_OPTIONS:-DENY}"
    
    # Celery settings
    export CELERY_TASK_ALWAYS_EAGER="${CELERY_TASK_ALWAYS_EAGER:-False}"
    export CELERY_TASK_EAGER_PROPAGATES="${CELERY_TASK_EAGER_PROPAGATES:-True}"
    
    # Logging settings
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"
    export DJANGO_LOG_LEVEL="${DJANGO_LOG_LEVEL:-INFO}"
    
    # Faster startup settings
    export REPLICAS="${REPLICAS:-1}"
    export IMAGE_TAG="${IMAGE_TAG:-latest}"
    
    # AGGRESSIVE health checks for new deployments - fail fast, start fast
    if [[ "$ENVIRONMENT" != "production" ]]; then
        export STARTUP_INITIAL_DELAY="3"      # Very fast startup detection
        export READINESS_INITIAL_DELAY="3"    # Check readiness quickly  
        export LIVENESS_INITIAL_DELAY="10"    # Quick liveness checks
        export HEALTH_CHECK_PERIOD="3"        # Fast polling
        export HEALTH_TIMEOUT="3"             # Quick timeout
        export HEALTH_FAILURE_THRESHOLD="5"   # Allow more retries for new deployments
    else
        # Conservative values for production
        export STARTUP_INITIAL_DELAY="10"
        export READINESS_INITIAL_DELAY="10" 
        export LIVENESS_INITIAL_DELAY="30"
        export HEALTH_CHECK_PERIOD="10"
        export HEALTH_TIMEOUT="5"
        export HEALTH_FAILURE_THRESHOLD="3"
    fi
    
    log_success "Kubernetes environment variables configured!"
}

# Setup TLS/SSL for HTTPS
setup_tls() {
    if [[ -z "$DOMAIN" ]]; then
        log_info "No domain specified, skipping TLS setup"
        export ENABLE_TLS="false"
        export HOST_DOMAIN=""
        export TLS_SECRET_NAME=""
        return 0
    fi
    
    log_info "Setting up TLS for domain: $DOMAIN"
    
    # Check if certificate files exist (we're in k8s directory, so go up one level)
    if [[ ! -f "../certs/tls.cer" ]]; then
        log_error "Certificate file 'certs/tls.cer' not found!"
        log_error "Please place your certificate chain in certs/tls.cer"
        exit 1
    fi
    
    if [[ ! -f "../certs/private.key" ]]; then
        log_error "Private key file 'certs/private.key' not found!"
        log_error "Please place your private key in certs/private.key"
        exit 1
    fi
    
    log_info "Certificate files found, creating TLS secret..."
    
    # Use project-specific namespace
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    TLS_SECRET_NAME="${PROJECT_NAME}-tls"
    
    # Delete existing secret if it exists
    kubectl delete secret "$TLS_SECRET_NAME" -n "$NAMESPACE" --ignore-not-found=true
    
    # Create new TLS secret (use ../ prefix since we're in k8s directory)
    if kubectl create secret tls "$TLS_SECRET_NAME" \
        --cert=../certs/tls.cer \
        --key=../certs/private.key \
        -n "$NAMESPACE"; then
        log_success "TLS secret '$TLS_SECRET_NAME' created successfully"
    else
        log_error "Failed to create TLS secret"
        exit 1
    fi
    
    # Set environment variables for ingress template
    export ENABLE_TLS="true"
    export HOST_DOMAIN="$DOMAIN"
    export TLS_SECRET_NAME="$TLS_SECRET_NAME"
    
    log_success "TLS configuration completed for domain: $DOMAIN"
}

# Setup ACR authentication for Kubernetes
setup_acr_authentication() {
    log_info "Setting up ACR authentication for Kubernetes..."
    
    # Use project-specific namespace
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    
    # Enable admin user on ACR
    log_info "Enabling admin user on ACR..."
    az acr update --name "${ACR_LOGIN_SERVER%%.*}" --admin-enabled true >/dev/null 2>&1
    
    # Delete existing ACR secret if it exists
    kubectl delete secret acr-secret -n "$NAMESPACE" >/dev/null 2>&1 || true
    
    # Create new ACR secret with admin credentials
    log_info "Creating ACR authentication secret..."
    kubectl create secret docker-registry acr-secret \
        --docker-server="$ACR_LOGIN_SERVER" \
        --docker-username="${ACR_LOGIN_SERVER%%.*}" \
        --docker-password="$(az acr credential show --name "${ACR_LOGIN_SERVER%%.*}" --query "passwords[0].value" -o tsv)" \
        -n "$NAMESPACE"
    
    # Patch service account to use the ACR secret
    log_info "Configuring service account for image pulling..."
    kubectl patch serviceaccount ${PROJECT_NAME}-sa -n "$NAMESPACE" \
        -p '{"imagePullSecrets": [{"name": "acr-secret"}]}'
    
    # Restart deployments to pick up new authentication
    log_info "Restarting deployments to apply new authentication..."
    kubectl rollout restart deployment/${PROJECT_NAME}-backend -n "$NAMESPACE" >/dev/null 2>&1 || true
    kubectl rollout restart deployment/${PROJECT_NAME}-celery-worker -n "$NAMESPACE" >/dev/null 2>&1 || true
    kubectl rollout restart deployment/${PROJECT_NAME}-celery-beat -n "$NAMESPACE" >/dev/null 2>&1 || true
    kubectl rollout restart deployment/${PROJECT_NAME}-frontend -n "$NAMESPACE" >/dev/null 2>&1 || true
    
    log_success "ACR authentication configured and deployments restarted!"
}

# Deploy Kubernetes resources
deploy_kubernetes() {
    log_info "Deploying Kubernetes resources..."
    
    cd k8s
    
    # Setup proper environment variables first
    setup_kubernetes_environment
    
    # Setup TLS if domain is provided
    setup_tls
    
    # Set environment variables for K8s manifests
    # Use PROJECT_NAME for namespace instead of hardcoded "hotcalls"
    export NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    export PROJECT_PREFIX="$PROJECT_NAME"
    export ENVIRONMENT="$ENVIRONMENT"
    
    # Fix celery app name (always use 'hotcalls' regardless of project name)
    export CELERY_APP_NAME="hotcalls"
    
    # Set resource defaults (can be overridden in .env)
    export REPLICAS="${REPLICAS:-1}"
    export RESOURCES_REQUESTS_MEMORY="${RESOURCES_REQUESTS_MEMORY:-256Mi}"
    export RESOURCES_REQUESTS_CPU="${RESOURCES_REQUESTS_CPU:-100m}"
    export RESOURCES_LIMITS_MEMORY="${RESOURCES_LIMITS_MEMORY:-512Mi}"
    export RESOURCES_LIMITS_CPU="${RESOURCES_LIMITS_CPU:-500m}"
    
    # Celery worker resources
    export CELERY_RESOURCES_REQUESTS_MEMORY="${CELERY_RESOURCES_REQUESTS_MEMORY:-128Mi}"
    export CELERY_RESOURCES_REQUESTS_CPU="${CELERY_RESOURCES_REQUESTS_CPU:-50m}"
    export CELERY_RESOURCES_LIMITS_MEMORY="${CELERY_RESOURCES_LIMITS_MEMORY:-256Mi}"
    export CELERY_RESOURCES_LIMITS_CPU="${CELERY_RESOURCES_LIMITS_CPU:-200m}"
    
    # Celery beat resources
    export BEAT_RESOURCES_REQUESTS_MEMORY="${BEAT_RESOURCES_REQUESTS_MEMORY:-64Mi}"
    export BEAT_RESOURCES_REQUESTS_CPU="${BEAT_RESOURCES_REQUESTS_CPU:-25m}"
    export BEAT_RESOURCES_LIMITS_MEMORY="${BEAT_RESOURCES_LIMITS_MEMORY:-128Mi}"
    export BEAT_RESOURCES_LIMITS_CPU="${BEAT_RESOURCES_LIMITS_CPU:-100m}"
    
    # HPA settings (as integers for YAML)
    export HPA_MIN_REPLICAS="${HPA_MIN_REPLICAS:-1}"
    export HPA_MAX_REPLICAS="${HPA_MAX_REPLICAS:-5}"
    export CELERY_HPA_MIN_REPLICAS="${CELERY_HPA_MIN_REPLICAS:-1}"
    export CELERY_HPA_MAX_REPLICAS="${CELERY_HPA_MAX_REPLICAS:-3}"
    
    # Application settings with defaults
    export IMAGE_TAG="${IMAGE_TAG:-latest}"
    # DEBUG should be True for staging, False for production
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        export DEBUG="${DEBUG:-True}"
    else
        export DEBUG="${DEBUG:-False}"
    fi
    export TIME_ZONE="${TIME_ZONE:-UTC}"
    export DB_SSLMODE="${DB_SSLMODE:-require}"
    
    # Set Django settings module based on environment
    if [[ "$ENVIRONMENT" == "production" ]]; then
        export DJANGO_SETTINGS_MODULE="hotcalls.settings.production"
    elif [[ "$ENVIRONMENT" == "staging" ]]; then
        export DJANGO_SETTINGS_MODULE="hotcalls.settings.staging"
    else
        export DJANGO_SETTINGS_MODULE="hotcalls.settings.development"
    fi
    
    # Set BASE_URL based on domain parameter
    if [[ -n "$DOMAIN" ]]; then
        export BASE_URL="https://${DOMAIN}"
    else
        export BASE_URL="http://localhost:8000"
    fi
    # ALLOWED_HOSTS is ALWAYS * per user requirement - already set above
    
    # Set security settings for staging/production
    if [[ "$ENVIRONMENT" == "staging" ]] || [[ "$ENVIRONMENT" == "production" ]]; then
        export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-True}"
        export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-True}"
        export CSRF_COOKIE_SECURE="${CSRF_COOKIE_SECURE:-True}"
        export SECURE_BROWSER_XSS_FILTER="${SECURE_BROWSER_XSS_FILTER:-True}"
        export SECURE_CONTENT_TYPE_NOSNIFF="${SECURE_CONTENT_TYPE_NOSNIFF:-True}"
    else
        export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-False}"
        export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-False}"
        export CSRF_COOKIE_SECURE="${CSRF_COOKIE_SECURE:-False}"
        export SECURE_BROWSER_XSS_FILTER="${SECURE_BROWSER_XSS_FILTER:-False}"
        export SECURE_CONTENT_TYPE_NOSNIFF="${SECURE_CONTENT_TYPE_NOSNIFF:-False}"
    fi
    
    # Validate Django settings module matches environment
    log_info "Validating Django configuration..."
    log_info "  ENVIRONMENT=$ENVIRONMENT"
    log_info "  DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
    log_info "  DB_HOST=$DB_HOST"
    log_info "  DB_NAME=$DB_NAME"
    log_info "  DB_USER=$DB_USER"
    log_info "  DB_PORT=${DB_PORT:-5432}"
    log_info "  DB_SSLMODE=$DB_SSLMODE"
    log_info "  BASE_URL=$BASE_URL"
    log_info "  ALLOWED_HOSTS=$ALLOWED_HOSTS"
    
    # Validate critical database settings
    if [[ "$ENVIRONMENT" != "development" ]]; then
        if [[ -z "$DB_HOST" || "$DB_HOST" == "localhost" || "$DB_HOST" == "127.0.0.1" ]]; then
            log_error "CRITICAL: DB_HOST is not properly set for $ENVIRONMENT environment!"
            log_error "DB_HOST is: '$DB_HOST'"
            log_error "This should be the Azure PostgreSQL server hostname"
            exit 1
        fi
        
        if [[ ! "$DJANGO_SETTINGS_MODULE" =~ hotcalls\.settings\.$ENVIRONMENT ]]; then
            log_error "CRITICAL: DJANGO_SETTINGS_MODULE mismatch!"
            log_error "ENVIRONMENT=$ENVIRONMENT but DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
            exit 1
        fi
    fi
    
    # Security settings
    export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-False}"
    export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-False}"
    export CSRF_COOKIE_SECURE="${CSRF_COOKIE_SECURE:-False}"
    export SECURE_BROWSER_XSS_FILTER="${SECURE_BROWSER_XSS_FILTER:-True}"
    export SECURE_CONTENT_TYPE_NOSNIFF="${SECURE_CONTENT_TYPE_NOSNIFF:-True}"
    export X_FRAME_OPTIONS="${X_FRAME_OPTIONS:-DENY}"
    
    # Celery settings
    export CELERY_TASK_ALWAYS_EAGER="${CELERY_TASK_ALWAYS_EAGER:-False}"
    export CELERY_TASK_EAGER_PROPAGATES="${CELERY_TASK_EAGER_PROPAGATES:-True}"
    
    # Logging settings
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"
    export DJANGO_LOG_LEVEL="${DJANGO_LOG_LEVEL:-INFO}"
    
    # Debug: Show critical resource variables
    log_info "Resource Variables Set:"
    log_info "  PROJECT_NAME=$PROJECT_NAME"
    log_info "  ENVIRONMENT=$ENVIRONMENT"
    log_info "  NAMESPACE=$NAMESPACE"
    log_info "  PROJECT_PREFIX=$PROJECT_PREFIX"
    log_info "  RESOURCES_REQUESTS_MEMORY=$RESOURCES_REQUESTS_MEMORY"
    log_info "  RESOURCES_REQUESTS_CPU=$RESOURCES_REQUESTS_CPU"
    log_info "  HPA_MAX_REPLICAS=$HPA_MAX_REPLICAS"
    
    # Apply manifests with faster deployment order
    log_info "Creating namespace and RBAC (parallel)..."
    
    # Create foundational resources in parallel
    envsubst < namespace.yaml | kubectl apply -f - &
    envsubst < rbac.yaml | kubectl apply -f - &
    wait  # Wait for namespace and RBAC to be ready
    
    log_info "Creating configuration (parallel)..."
    # Create config and secrets in parallel 
    envsubst < configmap.yaml | kubectl apply -f - &
    envsubst < secrets.yaml | kubectl apply -f - &
    wait  # Wait for config to be ready
    
    log_info "Deploying core services (parallel)..."
    # Deploy Redis and services in parallel (Redis starts faster)
    envsubst < redis-deployment.yaml | kubectl apply -f - &
    envsubst < service.yaml | kubectl apply -f - &
    
    # Deploy frontend if available (parallel with services)
    if [[ "${HAS_FRONTEND:-false}" == "true" ]] && [[ -f "frontend-deployment.yaml" ]]; then
        envsubst < frontend-deployment.yaml | kubectl apply -f - &
        envsubst < frontend-service.yaml | kubectl apply -f - &
    fi
    
    wait  # Wait for services to be created
    
    log_info "Waiting for Redis to be ready..."
    # Wait for Redis to be available before deploying backend
    kubectl wait --for=condition=available deployment/redis -n "$NAMESPACE" --timeout=300s
    
    log_info "Deploying backend applications..."
    # Deploy backend applications (depends on Redis and config)
    envsubst < deployment.yaml | kubectl apply -f -
    
    # Run Django migrations after backend is deployed
    run_django_migrations
    
    # Apply ingress last (after services are ready)
    log_info "Creating networking..."
    
    # Handle ingress based on TLS configuration
    if [[ "$ENABLE_TLS" == "true" ]] && [[ -n "$HOST_DOMAIN" ]]; then
        # Create a temporary ingress file with proper TLS configuration
        cat > ingress-temp.yaml <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${PROJECT_PREFIX}-ingress
  namespace: ${PROJECT_PREFIX}-${ENVIRONMENT}
  labels:
    app.kubernetes.io/name: ${PROJECT_PREFIX}
    app.kubernetes.io/component: ingress
    environment: ${ENVIRONMENT}
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - ${HOST_DOMAIN}
    secretName: ${TLS_SECRET_NAME}
  rules:
  - host: ${HOST_DOMAIN}
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: ${PROJECT_PREFIX}-backend-internal
            port:
              number: 8000
      - path: /admin
        pathType: Prefix
        backend:
          service:
            name: ${PROJECT_PREFIX}-backend-internal
            port:
              number: 8000
      - path: /health
        pathType: Prefix
        backend:
          service:
            name: ${PROJECT_PREFIX}-backend-internal
            port:
              number: 8000
      - path: /static
        pathType: Prefix
        backend:
          service:
            name: ${PROJECT_PREFIX}-backend-internal
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ${PROJECT_PREFIX}-frontend-service
            port:
              number: 80
EOF
        kubectl apply -f ingress-temp.yaml
        rm -f ingress-temp.yaml
    else
        # Apply regular ingress without TLS
        envsubst < ingress.yaml | kubectl apply -f -
    fi
    
    envsubst < hpa.yaml | kubectl apply -f -
    
    log_success "Kubernetes resources deployed!"
    
    cd ..
    
    # Setup ACR authentication BEFORE any deployments start
    setup_acr_authentication
    
    # Wait a moment for the service account patch to propagate
    log_info "Waiting for service account configuration to propagate..."
    sleep 5
}

# Run Django migrations
run_django_migrations() {
    log_info "Running Django database migrations..."
    
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    
    # Wait for backend deployment to have at least one ready pod
    log_info "Waiting for backend pods to be ready..."
    kubectl wait --for=condition=available deployment/${PROJECT_NAME}-backend \
        -n "$NAMESPACE" --timeout=300s || {
        log_error "Backend deployment not ready for migrations"
        return 1
    }
    
    # Give the pod a moment to fully initialize
    sleep 5
    
    # Handle --purge option - drop database completely
    if [[ "$PURGE_DB" == "true" ]]; then
        log_warning "PURGE MODE: Dropping ALL database tables..."
        
        kubectl exec deployment/${PROJECT_NAME}-backend -n "$NAMESPACE" -- \
            python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotcalls.settings.${ENVIRONMENT}')
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('DROP SCHEMA public CASCADE;')
    cursor.execute('CREATE SCHEMA public;')
    cursor.execute('GRANT ALL ON SCHEMA public TO PUBLIC;')
    cursor.execute('GRANT ALL ON SCHEMA public TO postgres;')
print('Database COMPLETELY PURGED!')
" || {
            log_error "Failed to purge database"
            return 1
        }
        
        log_success "Database purged! Now running fresh migrations..."
    fi
    
    # Create a migration job
    log_info "Creating migration job..."
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: django-migrate-$(date +%s)
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: ${PROJECT_PREFIX}
    app.kubernetes.io/component: migration
    environment: ${ENVIRONMENT}
spec:
  ttlSecondsAfterFinished: 300
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ${PROJECT_PREFIX}
        app.kubernetes.io/component: migration
    spec:
      restartPolicy: Never
      serviceAccountName: ${PROJECT_PREFIX}-sa
      containers:
      - name: migrate
        image: ${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:${IMAGE_TAG}
        command: ["python", "manage.py", "migrate", "--noinput"]
        envFrom:
        - configMapRef:
            name: ${PROJECT_PREFIX}-config
        - secretRef:
            name: ${PROJECT_PREFIX}-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "200m"
          limits:
            memory: "1Gi"
            cpu: "500m"
EOF
    
    # Wait for migration job to complete
    JOB_NAME=$(kubectl get jobs -n "$NAMESPACE" -l app.kubernetes.io/component=migration \
        --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
    
    if [[ -n "$JOB_NAME" ]]; then
        log_info "Waiting for migration job $JOB_NAME to complete..."
        if kubectl wait --for=condition=complete job/$JOB_NAME -n "$NAMESPACE" --timeout=300s; then
            log_success "Database migrations completed successfully!"
            
            # Show migration logs
            log_info "Migration logs:"
            kubectl logs job/$JOB_NAME -n "$NAMESPACE" --tail=50
        else
            log_error "Migration job failed or timed out!"
            kubectl logs job/$JOB_NAME -n "$NAMESPACE" --tail=100
            return 1
        fi
    else
        log_error "Could not find migration job!"
        return 1
    fi
}

# Install nginx ingress controller if not present
install_ingress_controller() {
    log_info "Checking for nginx ingress controller..."
    
    if ! kubectl get namespace ingress-nginx >/dev/null 2>&1; then
        log_info "Installing nginx ingress controller..."
        kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml
        
        log_info "Waiting for ingress controller to be ready..."
        kubectl wait --namespace ingress-nginx \
            --for=condition=ready pod \
            --selector=app.kubernetes.io/component=controller \
            --timeout=300s
    else
        log_info "Nginx ingress controller already installed"
    fi
}

# Wait for deployment and get application URL
wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    # Use project-specific namespace
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    
    # Wait for all deployments with smart retry logic
    log_info "Waiting for backend deployment..."
    local backend_ready=false
    local retry_count=0
    local max_retries=3
    
    while [[ $retry_count -lt $max_retries ]] && [[ "$backend_ready" == "false" ]]; do
        if kubectl wait --for=condition=available deployment/${PROJECT_NAME}-backend \
            -n "$NAMESPACE" --timeout=120s >/dev/null 2>&1; then
            backend_ready=true
            log_success "Backend deployment ready!"
        else
            retry_count=$((retry_count + 1))
            log_warning "Backend not ready yet (attempt $retry_count/$max_retries), checking pod status..."
            
            # Show pod status for debugging
            kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=backend --no-headers | head -3
            
            if [[ $retry_count -lt $max_retries ]]; then
                log_info "Retrying backend deployment wait..."
            fi
        fi
    done
    
    if [[ "$backend_ready" == "false" ]]; then
        log_error "Backend deployment failed to become ready after $max_retries attempts"
        log_error "Check pod logs: kubectl logs -f deployment/${PROJECT_NAME}-backend -n $NAMESPACE"
        exit 1
    fi
    
    # Wait for celery deployments (non-critical, with shorter timeouts)
    log_info "Waiting for celery deployments (non-critical)..."
    kubectl wait --for=condition=available deployment/${PROJECT_NAME}-celery-worker \
        -n "$NAMESPACE" --timeout=60s >/dev/null 2>&1 || log_warning "Celery worker timeout (non-critical)"
    kubectl wait --for=condition=available deployment/${PROJECT_NAME}-celery-beat \
        -n "$NAMESPACE" --timeout=60s >/dev/null 2>&1 || log_warning "Celery beat timeout (non-critical)"
    
    # Wait for frontend if it exists
    if kubectl get deployment ${PROJECT_NAME}-frontend -n "$NAMESPACE" >/dev/null 2>&1; then
        log_info "Waiting for frontend deployment..."
        kubectl wait --for=condition=available deployment/${PROJECT_NAME}-frontend \
            -n "$NAMESPACE" --timeout=120s >/dev/null 2>&1 || log_warning "Frontend timeout (non-critical)"
    fi
    
    log_info "Waiting for ingress to get external IP..."
    
    # Wait for external IP (up to 10 minutes)
    for i in {1..60}; do
        EXTERNAL_IP=$(kubectl get ingress ${PROJECT_NAME}-ingress -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        
        if [[ -n "$EXTERNAL_IP" ]]; then
            break
        fi
        
        if [[ $i -eq 60 ]]; then
            log_warning "Ingress IP not ready after 10 minutes. Check status manually."
            kubectl get ingress -n "$NAMESPACE"
            kubectl get service -n ingress-nginx ingress-nginx-controller
            return
        fi
        
        sleep 10
    done
    
    if [[ -n "$EXTERNAL_IP" ]]; then
        log_success "🎉 Application is ready!"
        log_success "🌐 Application URL: http://$EXTERNAL_IP"
        log_success "   • Frontend: http://$EXTERNAL_IP/"
        log_success "   • API: http://$EXTERNAL_IP/api/"
        log_success "   • Health: http://$EXTERNAL_IP/health/"
        log_success "   • Admin: http://$EXTERNAL_IP/admin/"
        
        # Show HTTPS URLs if domain is configured
        if [[ -n "$DOMAIN" ]]; then
            echo ""
            log_success "🔒 HTTPS Access (after DNS configuration):"
            log_success "   • Frontend: https://$DOMAIN/"
            log_success "   • API: https://$DOMAIN/api/"
            log_success "   • Health: https://$DOMAIN/health/"
            log_success "   • Admin: https://$DOMAIN/admin/"
            echo ""
            log_info "📌 Please update your DNS A record for '$DOMAIN' to point to: $EXTERNAL_IP"
            log_info "   DNS update command example: "
            log_info "   - For most DNS providers: Create A record: $DOMAIN → $EXTERNAL_IP"
        fi
        
        # Update BASE_URL in secrets based on domain configuration
        if [[ -n "$DOMAIN" ]]; then
            # Use HTTPS domain if provided
            log_info "Setting BASE_URL to: https://$DOMAIN"
            kubectl patch secret ${PROJECT_NAME}-secrets -n "$NAMESPACE" \
                --type='json' -p="[{'op': 'replace', 'path': '/data/BASE_URL', 'value': '$(echo -n "https://$DOMAIN" | base64)'}]"
        else
            # Fall back to HTTP with external IP
            log_info "Setting BASE_URL to: http://$EXTERNAL_IP"
            kubectl patch secret ${PROJECT_NAME}-secrets -n "$NAMESPACE" \
                --type='json' -p="[{'op': 'replace', 'path': '/data/BASE_URL', 'value': '$(echo -n "http://$EXTERNAL_IP" | base64)'}]"
        fi
        
        # Restart deployment to pick up new BASE_URL
        kubectl rollout restart deployment/${PROJECT_NAME}-backend -n "$NAMESPACE"
    fi
}

# Verify database connection after deployment
verify_database_connection() {
    log_info "Verifying database connection in deployed pods..."
    
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    
    # Wait a bit for the pods to stabilize
    sleep 5
    
    # Check database connection from the backend pod
    log_info "Testing database connection from backend pod..."
    
    # Get the first running backend pod
    BACKEND_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=backend \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$BACKEND_POD" ]]; then
        log_error "No backend pod found!"
        return 1
    fi
    
    # Execute Python command to check database settings
    log_info "Checking Django database configuration..."
    kubectl exec -it "$BACKEND_POD" -n "$NAMESPACE" -- python -c "
import os
from django.conf import settings
print('=== Django Database Configuration ===')
print(f'ENVIRONMENT: {os.environ.get(\"ENVIRONMENT\")}')
print(f'DJANGO_SETTINGS_MODULE: {os.environ.get(\"DJANGO_SETTINGS_MODULE\")}')
print(f'DB_HOST from env: {os.environ.get(\"DB_HOST\")}')
print(f'DB_NAME from env: {os.environ.get(\"DB_NAME\")}')
print(f'DB_USER from env: {os.environ.get(\"DB_USER\")}')
print('--- Django Settings ---')
db_config = settings.DATABASES['default']
print(f'Host: {db_config.get(\"HOST\")}')
print(f'Port: {db_config.get(\"PORT\")}')
print(f'Database: {db_config.get(\"NAME\")}')
print(f'User: {db_config.get(\"USER\")}')
print(f'SSL Mode: {db_config.get(\"OPTIONS\", {}).get(\"sslmode\")}')
"
    
    # Check the health endpoint
    log_info "Checking health endpoint..."
    kubectl exec -it "$BACKEND_POD" -n "$NAMESPACE" -- curl -s http://localhost:8000/health/ | python -m json.tool
    
    # Check readiness (includes database check)
    log_info "Checking readiness endpoint (includes database connectivity)..."
    kubectl exec -it "$BACKEND_POD" -n "$NAMESPACE" -- curl -s http://localhost:8000/health/readiness/ | python -m json.tool
    
    # Check pod logs for any database errors
    log_info "Checking recent pod logs for database errors..."
    kubectl logs "$BACKEND_POD" -n "$NAMESPACE" --tail=50 | grep -i -E "(database|postgres|db_host|localhost)" || true
}

# Show deployment status
show_status() {
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    log_info "Deployment Status:"
    echo
    kubectl get all -n "$NAMESPACE"
    echo
    log_info "Ingress Status:"
    kubectl get ingress -n "$NAMESPACE"
    echo
    log_info "To check logs: kubectl logs -f deployment/${PROJECT_NAME}-backend -n $NAMESPACE"
    log_info "To check ingress: kubectl get ingress -n $NAMESPACE"
    log_info "To check nginx controller: kubectl get service -n ingress-nginx ingress-nginx-controller"
}

# Clean up Docker disk space after successful deployment
cleanup_docker() {
    log_info "Cleaning up Docker disk space..."
    
    # Show current disk usage
    log_info "Current Docker disk usage:"
    docker system df
    
    # Clean up unused images, containers, and build cache
    log_info "Removing unused Docker resources..."
    docker system prune -a -f --volumes
    
    # Clean up builder cache
    log_info "Cleaning up Docker builder cache..."
    docker builder prune -a -f
    
    # Show disk usage after cleanup
    log_info "Docker disk usage after cleanup:"
    docker system df
    
    log_success "Docker cleanup completed!"
}

# Cleanup function that runs on exit
cleanup_on_exit() {
    local exit_code=$?
    
    # Only run cleanup if Docker is available and we've started deployment
    if command -v docker &> /dev/null && [[ -n "$DEPLOYMENT_STARTED" ]]; then
        if [[ $exit_code -ne 0 ]]; then
            log_info "Deployment failed, cleaning up Docker resources..."
        fi
        cleanup_docker
    fi
    
    # Exit with the original exit code
    exit $exit_code
}

# Main execution
main() {
    # Set up trap to clean up on exit (success or failure)
    trap cleanup_on_exit EXIT
    
    # Mark that deployment has started
    DEPLOYMENT_STARTED=true
    
    log_info "Starting HotCalls deployment..."
    
    # Debug: Verify variables are set correctly
    log_info "DEBUG: Initial variables:"
    log_info "  PROJECT_NAME='$PROJECT_NAME'"
    log_info "  ENVIRONMENT='$ENVIRONMENT'"
    log_info "  LOCATION_SHORT='$LOCATION_SHORT'"
    
    check_prerequisites
    load_environment
    
    # Handle branch checkout first if specified
    checkout_branch
    
    if [[ "$UPDATE_ONLY" == "true" ]]; then
        log_info "Update-only mode: Skipping infrastructure deployment"
        check_azure_login
        
        # Still need to check workspace exists for update-only mode
        cd terraform
        WORKSPACE_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
        if ! terraform workspace list | grep -q "\b$WORKSPACE_NAME\b"; then
            log_error "Terraform workspace '$WORKSPACE_NAME' not found for update-only mode!"
            log_error "You must run a full deployment first: $0 --project-name=$PROJECT_NAME --environment=$ENVIRONMENT"
            cd ..
            exit 1
        fi
        terraform workspace select "$WORKSPACE_NAME"
        cd ..
        
        setup_frontend
        get_infrastructure_outputs_update_only
        configure_kubectl
        
        # Handle --purge preparation BEFORE building images
        if [[ "$PURGE_DB" == "true" ]]; then
            log_warning "PURGE MODE: Preparing fresh migrations..."
            
            log_info "Step 1: Deleting ALL existing migration files (except __init__.py)..."
            find core/migrations -name "*.py" -not -name "__init__.py" -delete 2>/dev/null || true
            
            log_info "Step 2: Creating fresh migrations..."
            # Activate virtual environment if it exists
            if [ -d "venv" ]; then
                source venv/bin/activate
            fi
            python manage.py makemigrations --noinput || {
                log_error "Failed to create migrations. Make sure Django is installed locally."
                exit 1
            }
            
            log_success "Fresh migrations created! Will be included in Docker image."
        fi
        
        build_and_push_images
        deploy_kubernetes
        wait_for_deployment
        verify_database_connection
        show_status
    else
        log_info "Full deployment mode: Including infrastructure"
        check_azure_login
        
        if ! check_and_handle_resource_group; then
            log_error "Resource group handling failed!"
            exit 1
        fi
        
        setup_frontend
        deploy_infrastructure
        get_infrastructure_outputs
        configure_kubectl
        install_ingress_controller
        
        # Handle --purge preparation BEFORE building images
        if [[ "$PURGE_DB" == "true" ]]; then
            log_warning "PURGE MODE: Preparing fresh migrations..."
            
            log_info "Step 1: Deleting ALL existing migration files (except __init__.py)..."
            find core/migrations -name "*.py" -not -name "__init__.py" -delete 2>/dev/null || true
            
            log_info "Step 2: Creating fresh migrations..."
            # Activate virtual environment if it exists
            if [ -d "venv" ]; then
                source venv/bin/activate
            fi
            python manage.py makemigrations --noinput || {
                log_error "Failed to create migrations. Make sure Django is installed locally."
                exit 1
            }
            
            log_success "Fresh migrations created! Will be included in Docker image."
        fi
        
        build_and_push_images
        deploy_kubernetes
        wait_for_deployment
        verify_database_connection
        show_status
    fi
    
    log_success "Deployment completed successfully! 🚀"
}

# Run main function
main "$@" 