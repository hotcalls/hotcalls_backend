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
# - SPEED OPTIMIZATIONS:
#   * Docker build caching for faster image builds
#   * Parallel Kubernetes resource deployment
#   * Fixed environment variable substitution (ALLOWED_HOSTS, etc.)
#   * Reduced health check timeouts for staging/dev
#   * Optimized deployment order (Redis first, then backend)
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
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --project-name=hotcalls-prod           # Deploy to resource group: hotcalls-prod"
            echo "  $0 --project-name=myapp --environment=dev # Deploy to resource group: myapp (dev environment)"  
            echo "  $0 --project-name=test-rg --update-only   # Update K8s only in test-rg"
            echo "  $0 --project-name=staging --branch=main   # Deploy staging with main branch"
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
if [[ -n "$BRANCH" ]]; then
    echo "   Branch: $BRANCH"
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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if required tools are installed
    command -v az >/dev/null 2>&1 || { log_error "Azure CLI is required but not installed. Aborting."; exit 1; }
    command -v terraform >/dev/null 2>&1 || { log_error "Terraform is required but not installed. Aborting."; exit 1; }
    command -v kubectl >/dev/null 2>&1 || { log_error "kubectl is required but not installed. Aborting."; exit 1; }
    command -v docker >/dev/null 2>&1 || { log_error "Docker is required but not installed. Aborting."; exit 1; }
    command -v envsubst >/dev/null 2>&1 || { log_error "envsubst is required but not installed. Aborting."; exit 1; }
    command -v git >/dev/null 2>&1 || { log_error "git is required but not installed. Aborting."; exit 1; }
    
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
    
    # Check if .env file exists
    if [[ ! -f ".env" ]]; then
        log_error ".env file not found. Please create it with your configuration."
        exit 1
    fi
    
    log_success "All prerequisites met!"
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
    
    # Check if frontend repository URL is configured
    if [[ -z "${FRONTEND_REPO_URL:-}" ]]; then
        log_warning "No frontend repository configured. Skipping frontend setup."
        return 0
    fi
    
    # Check if dist directory already exists
    if [[ -d "dist" ]]; then
        log_info "Frontend dist/ directory already exists. Skipping build."
        return 0
    fi
    
    # Check if frontend source already exists
    if [[ ! -d "frontend" ]]; then
        log_info "Cloning frontend repository..."
        
        # Clone the private repository
        if ! git clone "$FRONTEND_REPO_URL" frontend; then
            log_error "Failed to clone frontend repository. Please ensure:"
            log_error "1. Your SSH key is added to your GitHub account"
            log_error "2. The repository URL is correct: $FRONTEND_REPO_URL"
            log_error "3. You have access to the private repository"
            exit 1
        fi
        
        # If branch is specified, checkout that branch after cloning
        if [[ -n "$BRANCH" ]]; then
            cd frontend
            git fetch origin
            if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
                git checkout -b "$BRANCH" "origin/$BRANCH"
                log_info "Checked out frontend to branch: $BRANCH"
            else
                log_warning "Branch '$BRANCH' not found in frontend repository, using default branch"
            fi
            cd ..
        fi
        
        log_success "Frontend repository cloned!"
    else
        log_info "Frontend directory exists. Branch checkout already handled."
    fi
    
    # Build the frontend
    log_info "Building frontend..."
    cd frontend
    
    # Check if package.json exists
    if [[ ! -f "package.json" ]]; then
        log_error "No package.json found in frontend directory"
        exit 1
    fi
    
    # Install dependencies
    log_info "Installing frontend dependencies..."
    if command -v npm >/dev/null 2>&1; then
        npm install
    elif command -v yarn >/dev/null 2>&1; then
        yarn install
    else
        log_error "Neither npm nor yarn found. Please install Node.js and npm"
        exit 1
    fi
    
    # Build the project
    log_info "Building frontend project..."
    if npm run build; then
        log_success "Frontend built successfully!"
    else
        log_error "Frontend build failed"
        exit 1
    fi
    
    # Copy build output to expected location
    if [[ -d "dist" ]]; then
        cp -r dist ../
        log_info "Copied dist/ to project root"
    elif [[ -d "build" ]]; then
        cp -r build ../dist
        log_info "Copied build/ to project root as dist/"
    else
        log_error "No dist/ or build/ directory found after frontend build"
        exit 1
    fi
    
    cd ..
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
    
    # Attach ACR to AKS cluster for image pulling
    log_info "Attaching ACR to AKS cluster..."
    az aks update \
        --name "$AKS_CLUSTER_NAME" \
        --resource-group "$AKS_RESOURCE_GROUP" \
        --attach-acr "${ACR_LOGIN_SERVER%%.*}" \
        --only-show-errors
    
    log_success "ACR attached to AKS cluster!"
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
    # Use cache for faster builds
    docker buildx build --platform linux/amd64 \
        --cache-from=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:cache" \
        --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:cache,mode=max" \
        -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-backend:${IMAGE_TAG}" . --push
    
    # Build frontend image if dist directory exists
    if [[ -d "dist" ]]; then
        log_info "Building frontend image for AMD64 architecture..."
        # Use cache for faster builds
        docker buildx build --platform linux/amd64 \
            --cache-from=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:cache" \
            --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:cache,mode=max" \
            -f frontend-deploy/Dockerfile -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-frontend:${IMAGE_TAG}" . --push
        
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
    
    # Fix environment variable substitution issues
    export ALLOWED_HOSTS="*"  # Allow all hosts (fix for pod IPs)
    export CORS_ALLOW_ALL_ORIGINS="${CORS_ALLOW_ALL_ORIGINS:-False}"
    export DEBUG="${DEBUG:-False}"
    export TIME_ZONE="${TIME_ZONE:-UTC}"
    export DB_SSLMODE="${DB_SSLMODE:-require}"
    
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
    
    # Faster health checks for development/staging
    if [[ "$ENVIRONMENT" != "production" ]]; then
        export STARTUP_INITIAL_DELAY="5"      # Reduced from 10
        export READINESS_INITIAL_DELAY="5"    # Reduced from 10  
        export LIVENESS_INITIAL_DELAY="15"    # Reduced from 30
        export HEALTH_CHECK_PERIOD="5"        # Reduced periods
    else
        # Keep conservative values for production
        export STARTUP_INITIAL_DELAY="10"
        export READINESS_INITIAL_DELAY="10" 
        export LIVENESS_INITIAL_DELAY="30"
        export HEALTH_CHECK_PERIOD="10"
    fi
    
    log_success "Kubernetes environment variables configured!"
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
    export DEBUG="${DEBUG:-False}"
    export TIME_ZONE="${TIME_ZONE:-UTC}"
    export DB_SSLMODE="${DB_SSLMODE:-require}"
    
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
    
    log_info "Deploying backend applications..."
    # Deploy backend applications (depends on Redis and config)
    envsubst < deployment.yaml | kubectl apply -f -
    
    log_info "Creating networking..."
    # Create ingress and HPA last
    envsubst < ingress.yaml | kubectl apply -f - &
    envsubst < hpa.yaml | kubectl apply -f - &
    wait
    
    log_success "Kubernetes resources deployed!"
    
    cd ..
    
    # Setup ACR authentication after K8s resources are created
    setup_acr_authentication
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
    
    # Wait for all deployments to be ready
    log_info "Waiting for backend deployment..."
    kubectl wait --for=condition=available deployment/${PROJECT_NAME}-backend \
        -n "$NAMESPACE" --timeout=600s
    
    log_info "Waiting for celery deployments..."
    kubectl wait --for=condition=available deployment/${PROJECT_NAME}-celery-worker \
        -n "$NAMESPACE" --timeout=300s || log_warning "Celery worker deployment timeout (non-critical)"
    kubectl wait --for=condition=available deployment/${PROJECT_NAME}-celery-beat \
        -n "$NAMESPACE" --timeout=300s || log_warning "Celery beat deployment timeout (non-critical)"
    
    # Wait for frontend if it exists
    if kubectl get deployment ${PROJECT_NAME}-frontend -n "$NAMESPACE" >/dev/null 2>&1; then
        log_info "Waiting for frontend deployment..."
        kubectl wait --for=condition=available deployment/${PROJECT_NAME}-frontend \
            -n "$NAMESPACE" --timeout=300s || log_warning "Frontend deployment timeout (non-critical)"
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
        
        # Update BASE_URL in secrets with the actual ingress IP
        kubectl patch secret ${PROJECT_NAME}-secrets -n "$NAMESPACE" \
            --type='json' -p="[{'op': 'replace', 'path': '/data/BASE_URL', 'value': '$(echo -n "http://$EXTERNAL_IP" | base64)'}]"
        
        # Restart deployment to pick up new BASE_URL
        kubectl rollout restart deployment/${PROJECT_NAME}-backend -n "$NAMESPACE"
    fi
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

# Main execution
main() {
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
        build_and_push_images
        deploy_kubernetes
        wait_for_deployment
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
        build_and_push_images
        deploy_kubernetes
        wait_for_deployment
        show_status
    fi
    
    log_success "Deployment completed successfully! 🚀"
}

# Run main function
main "$@" 