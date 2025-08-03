#!/bin/bash

# HotCalls Pure .env Deployment Script
# This script deploys the entire application stack to Azure using Terraform and Kubernetes
# ALL CONFIGURATION via .env file - no command line parameters
#
# FEATURES:
# - Pure .env configuration (no command line complexity)
# - Multi-repository support (backend, frontend, outbound agent)
# - Automatic repository cloning and branch management
# - Comprehensive resource configuration
# - Retry logic for failed deployments
# - Better error handling and cleanup
# - Automatic ACR authentication setup for Kubernetes
# - Fixed image naming consistency (project-specific names)
# - Automatic deployment restart after auth configuration
# 
# SPEED & RELIABILITY OPTIMIZATIONS:
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
#   ./deploy.sh
#
# CONFIGURATION:
#   Edit .env file with PROJECT_NAME, ENVIRONMENT, and all deployment settings

set -euo pipefail

# Pure .env Configuration - No Command Line Parameters
# All configuration loaded from .env file

# Handle help request
if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    echo "🚀 HotCalls Deployment Script - Pure .env Configuration"
            echo ""
    echo "Usage: $0"
            echo ""
    echo "📝 All configuration is managed via .env file:"
    echo "   - PROJECT_NAME: Azure resource group name"
    echo "   - ENVIRONMENT: staging/production/development"
    echo "   - All deployment flags: UPDATE_ONLY, NO_CACHE, PURGE_DB, etc."
    echo "   - Repository branches: BRANCH_BACKEND, BRANCH_FRONTEND, BRANCH_AGENT"
    echo "   - Resource settings: CPU, memory, replicas"
            echo ""
    echo "📋 Examples:"
    echo "   ./deploy.sh                    # Deploy using .env configuration"
    echo "   cp .env.staging .env && ./deploy.sh  # Deploy staging environment"
    echo ""
    echo "🔧 To customize deployment:"
    echo "   1. Edit .env file with your settings"
    echo "   2. Run: ./deploy.sh"
    echo ""
            exit 0
fi

# Reject any command line parameters (pure .env approach)
if [[ $# -gt 0 ]]; then
    echo "❌ This deployment script uses pure .env configuration"
    echo ""
    echo "❗ Command line parameters are no longer supported."
    echo "   Please configure all settings in your .env file."
    echo ""
    echo "📝 Edit .env file and set:"
    echo "   PROJECT_NAME=your-project-name"
    echo "   ENVIRONMENT=staging"
    echo "   # ... other settings"
    echo ""
    echo "Then run: ./deploy.sh"
    echo ""
    echo "Use --help for more information."
    exit 1
fi



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

# Enhanced environment loading with hierarchy and deployment configuration
load_environment() {
    log_info "Loading deployment configuration..."
    
    # Load base configuration
    if [[ -f ".env" ]]; then
        log_info "Loading base configuration from .env"
        set -a
    source .env
        set +a
    else
        log_error ".env file not found!"
        exit 1
    fi
    
    # Load environment-specific overrides
    local env_file=".env.${ENVIRONMENT}"
    if [[ -f "$env_file" ]]; then
        log_info "Loading environment overrides from $env_file"
        set -a
        source "$env_file"
        set +a
    fi
    
    # Load local overrides (developer-specific)
    if [[ -f ".env.local" ]]; then
        log_info "Loading local overrides from .env.local"
        set -a
        source .env.local
        set +a
    fi
    
    # Set branch defaults if not specified
    BRANCH_BACKEND=${BRANCH_BACKEND:-${BRANCH_FALLBACK:-main}}
    BRANCH_FRONTEND=${BRANCH_FRONTEND:-${BRANCH_FALLBACK:-main}}
    BRANCH_AGENT=${BRANCH_AGENT:-${BRANCH_FALLBACK:-main}}
    BRANCH_MCP=${BRANCH_MCP:-${BRANCH_FALLBACK:-main}}
    
    # Override command line flags from .env if not already set
    UPDATE_ONLY=${UPDATE_ONLY:-false}
    NO_CACHE=${NO_CACHE:-false}
    PURGE_DB=${PURGE_DB:-false}
    DRY_RUN=${DRY_RUN:-false}
    VERBOSE_LOGGING=${VERBOSE_LOGGING:-false}
    
    # Validate and show configuration
    validate_deployment_config
    show_deployment_config_summary
    
    log_success "Deployment configuration loaded!"
}

# Configuration validation
validate_deployment_config() {
    log_info "Validating deployment configuration..."
    
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
        "LIVEKIT_URL"
        "LIVEKIT_API_KEY"
        "LIVEKIT_API_SECRET"
    )
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required environment variable $var is not set in .env"
            exit 1
        fi
    done
    
    # Validate numeric values
    local numeric_vars=(
        "BACKEND_REPLICAS" "FRONTEND_REPLICAS" "OUTBOUNDAGENT_REPLICAS"
        "CELERY_WORKER_REPLICAS" "DEPLOYMENT_TIMEOUT"
    )
    
    for var in "${numeric_vars[@]}"; do
        if [[ -n "${!var:-}" ]] && ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
            log_error "Invalid numeric value for $var: ${!var}"
            exit 1
        fi
    done
    
    # Validate boolean values
    local boolean_vars=(
        "UPDATE_ONLY" "NO_CACHE" "PURGE_DB" "VERBOSE_LOGGING" "DRY_RUN"
        "BUILD_BACKEND" "BUILD_FRONTEND" "BUILD_OUTBOUNDAGENT"
        "BACKEND_HPA_ENABLED" "OUTBOUNDAGENT_HPA_ENABLED"
    )
    
    for var in "${boolean_vars[@]}"; do
        if [[ -n "${!var:-}" ]] && ! [[ "${!var}" =~ ^(true|false)$ ]]; then
            log_error "Invalid boolean value for $var: ${!var}. Must be 'true' or 'false'"
            exit 1
        fi
    done
    
    log_success "Configuration validation passed!"
}

# Configuration summary display
show_deployment_config_summary() {
    if [[ "${VERBOSE_LOGGING:-false}" == "true" ]]; then
        log_info "🚀 DEPLOYMENT CONFIGURATION SUMMARY:"
        echo ""
        log_info "📦 SERVICE SCALING:"
        log_info "  Backend: ${BACKEND_REPLICAS:-2} replicas (${BACKEND_CPU_REQUEST:-250m}/${BACKEND_CPU_LIMIT:-1000m} CPU, ${BACKEND_MEMORY_REQUEST:-512Mi}/${BACKEND_MEMORY_LIMIT:-2Gi} RAM)"
        log_info "  Frontend: ${FRONTEND_REPLICAS:-1} replicas (${FRONTEND_CPU_REQUEST:-100m}/${FRONTEND_CPU_LIMIT:-500m} CPU, ${FRONTEND_MEMORY_REQUEST:-128Mi}/${FRONTEND_MEMORY_LIMIT:-512Mi} RAM)"
        log_info "  Agent: ${OUTBOUNDAGENT_REPLICAS:-1} replicas (${OUTBOUNDAGENT_CPU_REQUEST:-500m}/${OUTBOUNDAGENT_CPU_LIMIT:-2000m} CPU, ${OUTBOUNDAGENT_MEMORY_REQUEST:-1Gi}/${OUTBOUNDAGENT_MEMORY_LIMIT:-4Gi} RAM)"
        
        log_info "🌿 BRANCH CONFIGURATION:"
        log_info "  Backend: $BRANCH_BACKEND"
        log_info "  Frontend: $BRANCH_FRONTEND"
        log_info "  Agent: $BRANCH_AGENT"
        
        log_info "⚙️ DEPLOYMENT MODE:"
        log_info "  Update Only: ${UPDATE_ONLY}"
        log_info "  No Cache: ${NO_CACHE}"
        log_info "  Purge DB: ${PURGE_DB}"
        log_info "  Parallel Deployment: ${DEPLOYMENT_PARALLEL:-true}"
        
        if [[ "${DRY_RUN:-false}" == "true" ]]; then
            log_warning "🔍 DRY RUN MODE - No changes will be applied!"
        fi
        
        echo ""
    else
        log_info "Environment: $ENVIRONMENT | Backend: ${BACKEND_REPLICAS:-2} replicas | Agent: ${OUTBOUNDAGENT_REPLICAS:-1} replicas"
        if [[ "${DRY_RUN:-false}" == "true" ]]; then
            log_warning "🔍 DRY RUN MODE"
        fi
    fi
}

# Enhanced multi-repository branch management
checkout_and_pull_repositories() {
    log_info "Managing repository branches from .env configuration..."
    
    # 1. Handle BACKEND repository (current directory)
    manage_backend_repository "$BRANCH_BACKEND"
    
    # 2. Handle FRONTEND repository
    if [[ -n "${FRONTEND_REPO_URL:-}" ]]; then
        manage_frontend_repository "$BRANCH_FRONTEND"
    else
        log_info "FRONTEND_REPO_URL not set, skipping frontend repository"
    fi
    
    # 3. Handle OUTBOUND AGENT repository
    if [[ -n "${OUTBOUNDAGENT_REPO_URL:-}" ]]; then
        manage_agent_repository "$BRANCH_AGENT"
    else
        log_info "OUTBOUNDAGENT_REPO_URL not set, skipping agent repository"
    fi
    
    # 4. Handle GOOGLE CALENDAR MCP repository
    if [[ -n "${GOOGLE_CALENDAR_MCP_REPO_URL:-}" ]]; then
        manage_google_calendar_mcp_repository "$BRANCH_MCP"
    else
        log_info "GOOGLE_CALENDAR_MCP_REPO_URL not set, skipping Google Calendar MCP repository"
    fi
    
    log_success "All repositories updated successfully!"
}

# Backend repository management (current directory)
manage_backend_repository() {
    local target_branch="$1"
    
    log_info "📦 Managing Backend Repository (branch: $target_branch)..."
    
    # Fetch latest from origin
    git fetch origin
    
    # Check if branch exists locally
    if git show-ref --verify --quiet refs/heads/$target_branch; then
        log_info "Local branch '$target_branch' exists, checking out and pulling..."
        git checkout "$target_branch"
        git pull origin "$target_branch" || log_warning "Failed to pull $target_branch from origin"
    elif git show-ref --verify --quiet refs/remotes/origin/$target_branch; then
        log_info "Remote branch 'origin/$target_branch' exists, creating local tracking branch..."
        git checkout -b "$target_branch" "origin/$target_branch"
    else
        log_warning "Branch '$target_branch' not found, staying on current branch"
        local current_branch=$(git branch --show-current)
        git pull origin "$current_branch" || log_warning "Failed to pull current branch"
    fi
    
    log_success "Backend repository updated to branch: $(git branch --show-current)"
}

# Frontend repository management
manage_frontend_repository() {
    local target_branch="$1"
    
    log_info "🎨 Managing Frontend Repository (branch: $target_branch)..."
    
    # Clone or update frontend repository
    if [[ ! -d "frontend" ]]; then
        log_info "Cloning frontend repository: $FRONTEND_REPO_URL"
        git clone "$FRONTEND_REPO_URL" frontend
        cd frontend
    else
        log_info "Frontend repository exists, updating..."
            cd frontend
            git fetch origin
    fi
    
    # Branch management
    if git show-ref --verify --quiet refs/heads/$target_branch; then
        log_info "Local branch '$target_branch' exists, checking out and pulling..."
        git checkout "$target_branch"
        git pull origin "$target_branch" || log_warning "Failed to pull $target_branch from origin"
    elif git show-ref --verify --quiet refs/remotes/origin/$target_branch; then
        log_info "Remote branch 'origin/$target_branch' exists, creating local tracking branch..."
        git checkout -b "$target_branch" "origin/$target_branch"
    else
        log_warning "Branch '$target_branch' not found, staying on current branch"
        local current_branch=$(git branch --show-current)
        git pull origin "$current_branch" || log_warning "Failed to pull current branch"
    fi
    
    cd ..
    log_success "Frontend repository updated to branch: $(cd frontend && git branch --show-current)"
}

# Outbound agent repository management
manage_agent_repository() {
    local target_branch="$1"
    
    log_info "🤖 Managing Outbound Agent Repository (branch: $target_branch)..."
    
    # Clone or update agent repository
    if [[ ! -d "outboundagent" ]]; then
        log_info "Cloning outbound agent repository: $OUTBOUNDAGENT_REPO_URL"
        git clone "$OUTBOUNDAGENT_REPO_URL" outboundagent
        cd outboundagent
    else
        log_info "Outbound agent repository exists, updating..."
        cd outboundagent
        git fetch origin
    fi
    
    # Branch management
    if git show-ref --verify --quiet refs/heads/$target_branch; then
        log_info "Local branch '$target_branch' exists, checking out and pulling..."
        git checkout "$target_branch"
        git pull origin "$target_branch" || log_warning "Failed to pull $target_branch from origin"
    elif git show-ref --verify --quiet refs/remotes/origin/$target_branch; then
        log_info "Remote branch 'origin/$target_branch' exists, creating local tracking branch..."
        git checkout -b "$target_branch" "origin/$target_branch"
    else
        log_warning "Branch '$target_branch' not found, staying on current branch"
        local current_branch=$(git branch --show-current)
        git pull origin "$current_branch" || log_warning "Failed to pull current branch"
    fi
    
    cd ..
    log_success "Outbound agent repository updated to branch: $(cd outboundagent && git branch --show-current)"
}

# Google Calendar MCP repository management
manage_google_calendar_mcp_repository() {
    local target_branch="$1"
    
    log_info "📅 Managing Google Calendar MCP Repository (branch: $target_branch)..."
    
    # Clone or update Google Calendar MCP repository
    if [[ ! -d "google-calendar-mcp" ]]; then
        log_info "Cloning Google Calendar MCP repository: $GOOGLE_CALENDAR_MCP_REPO_URL"
        git clone "$GOOGLE_CALENDAR_MCP_REPO_URL" google-calendar-mcp
        cd google-calendar-mcp
    else
        log_info "Google Calendar MCP repository exists, updating..."
        cd google-calendar-mcp
        git fetch origin
    fi
    
    # Branch management
    if git show-ref --verify --quiet refs/heads/$target_branch; then
        log_info "Local branch '$target_branch' exists, checking out and pulling..."
        git checkout "$target_branch"
        git pull origin "$target_branch" || log_warning "Failed to pull $target_branch from origin"
    elif git show-ref --verify --quiet refs/remotes/origin/$target_branch; then
        log_info "Remote branch 'origin/$target_branch' exists, creating local tracking branch..."
        git checkout -b "$target_branch" "origin/$target_branch"
    else
        log_warning "Branch '$target_branch' not found, staying on current branch"
        local current_branch=$(git branch --show-current)
        git pull origin "$current_branch" || log_warning "Failed to pull current branch"
    fi
    
    cd ..
    log_success "Google Calendar MCP repository updated to branch: $(cd google-calendar-mcp && git branch --show-current)"
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
    
    # Export variables for Kubernetes envsubst (not just Terraform)
    export REDIS_PASSWORD
    export SECRET_KEY
    export DB_NAME
    export DB_USER  
    export DB_PASSWORD
    export DB_HOST
    export DB_PORT="${DB_PORT:-5432}"
    export EMAIL_BACKEND
    export EMAIL_HOST
    export EMAIL_PORT
    export EMAIL_USE_TLS
    export EMAIL_USE_SSL
    export EMAIL_HOST_USER
    export EMAIL_HOST_PASSWORD
    export DEFAULT_FROM_EMAIL
    export SERVER_EMAIL
    export BASE_URL
    export LIVEKIT_URL
    export LIVEKIT_API_KEY
    export LIVEKIT_API_SECRET
    export TRUNK_ID
    export SIP_PROVIDER
    export STRIPE_SECRET_KEY
    export STRIPE_PUBLISHABLE_KEY
    export STRIPE_WEBHOOK_SECRET
    export META_APP_ID
    export META_APP_SECRET
    export META_REDIRECT_URI
    export META_API_VERSION
    export META_WEBHOOK_VERIFY_TOKEN
    
    # LiveKit Agent Configuration
    export LIVEKIT_AGENT_NAME
    
    # Outbound Agent API Keys
    export OPENAI_API_KEY
    export DEEPGRAM_API_KEY
    export ELEVEN_API_KEY
    export ELEVEN_VOICE_ID
    
    # MCP Server Configuration
    export MCP_SERVER_URL
    
    # Agent Configuration
    export AGENT_NAME
    export NAME
    export RING_DURATION
    export ENABLE_BACKGROUND_AUDIO
    export OFFICE_AMBIENCE_VOLUME
    export TYPING_SOUND_VOLUME
    export SIP_PROVIDER
    export TRUNK_ID
    
    # Call Log Configuration
    export CALL_LOG_ENDPOINT_URL
    export CALL_LOG_TIMEOUT
    export CALL_LOG_MAX_RETRIES
    
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
    
    # Direct Storage configuration (CDN removed)
    export CDN_ENDPOINT_FQDN=$(terraform output -raw cdn_endpoint_fqdn 2>/dev/null || echo "")
    export CDN_ENDPOINT_URL=$(terraform output -raw cdn_endpoint_url 2>/dev/null || echo "")
    
    # Set AZURE_CUSTOM_DOMAIN for Django to use direct storage (CDN has issues)
    export AZURE_CUSTOM_DOMAIN="$AZURE_ACCOUNT_NAME.blob.core.windows.net"
    log_info "Using direct storage domain: $AZURE_ACCOUNT_NAME.blob.core.windows.net (CDN disabled temporarily)"
    
    # Configure CORS for Azure Storage to allow frontend audio playback
    log_info "Configuring CORS for Azure Storage..."
    if [[ -n "$DOMAIN" ]]; then
        CORS_ORIGINS="https://$DOMAIN"
    else
        CORS_ORIGINS="https://app.hotcalls.de"
    fi
    
    # Add CORS configuration for blob storage
    az storage cors add \
        --account-name "$AZURE_ACCOUNT_NAME" \
        --account-key "$AZURE_STORAGE_KEY" \
        --services b \
        --methods GET POST PUT OPTIONS \
        --origins "$CORS_ORIGINS" "http://localhost:3000" "http://localhost:5173" \
        --allowed-headers "*" \
        --exposed-headers "*" \
        --max-age 3600 \
        2>/dev/null || log_info "CORS rules may already exist"
    
    log_info "✅ CORS configured for: $CORS_ORIGINS"
    
    # Set optional Azure variables with defaults
    export AZURE_CLIENT_ID="${AZURE_CLIENT_ID:-}"
    export AZURE_KEY_VAULT_URL="${AZURE_KEY_VAULT_URL:-}"
    export AZURE_MONITOR_CONNECTION_STRING="${AZURE_MONITOR_CONNECTION_STRING:-}"
    
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
    
    # Direct Storage configuration (CDN removed)
    export CDN_ENDPOINT_FQDN=$(terraform output -raw cdn_endpoint_fqdn 2>/dev/null || echo "")
    export CDN_ENDPOINT_URL=$(terraform output -raw cdn_endpoint_url 2>/dev/null || echo "")
    
    # Set AZURE_CUSTOM_DOMAIN for Django to use direct storage (CDN has issues)
    export AZURE_CUSTOM_DOMAIN="$AZURE_ACCOUNT_NAME.blob.core.windows.net"
    log_info "Using direct storage domain: $AZURE_ACCOUNT_NAME.blob.core.windows.net (CDN disabled temporarily)"
    
    # Configure CORS for Azure Storage to allow frontend audio playback
    log_info "Configuring CORS for Azure Storage..."
    if [[ -n "$DOMAIN" ]]; then
        CORS_ORIGINS="https://$DOMAIN"
    else
        CORS_ORIGINS="https://app.hotcalls.de"
    fi
    
    # Add CORS configuration for blob storage
    az storage cors add \
        --account-name "$AZURE_ACCOUNT_NAME" \
        --account-key "$AZURE_STORAGE_KEY" \
        --services b \
        --methods GET POST PUT OPTIONS \
        --origins "$CORS_ORIGINS" "http://localhost:3000" "http://localhost:5173" \
        --allowed-headers "*" \
        --exposed-headers "*" \
        --max-age 3600 \
        2>/dev/null || log_info "CORS rules may already exist"
    
    log_info "✅ CORS configured for: $CORS_ORIGINS"
    
    # Set optional Azure variables with defaults
    export AZURE_CLIENT_ID="${AZURE_CLIENT_ID:-}"
    export AZURE_KEY_VAULT_URL="${AZURE_KEY_VAULT_URL:-}"
    export AZURE_MONITOR_CONNECTION_STRING="${AZURE_MONITOR_CONNECTION_STRING:-}"
    
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
    
    # Build outbound agent image if enabled and directory exists
    if [[ "${BUILD_OUTBOUNDAGENT:-true}" == "true" ]] && [[ -d "outboundagent" ]]; then
        log_info "Building outbound agent image for AMD64 architecture..."
        
        cd outboundagent
        
        # Create Dockerfile if it doesn't exist
        if [[ ! -f "Dockerfile" ]]; then
            log_info "Creating Dockerfile for outbound agent..."
            create_agent_dockerfile
        fi
        
        if [[ "$NO_CACHE" == "true" ]]; then
            log_info "Building agent WITHOUT cache (--no-cache flag enabled)..."
            docker buildx build --platform linux/amd64 \
                --no-cache \
                -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:${IMAGE_TAG}" . --push
        else
            # Optimize for new projects - skip cache lookup on first build
            if docker manifest inspect "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:cache" >/dev/null 2>&1; then
                log_info "Using existing agent cache for faster build..."
                docker buildx build --platform linux/amd64 \
                    --cache-from=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:cache" \
                    --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:cache,mode=max" \
                    -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:${IMAGE_TAG}" . --push
            else
                log_info "First agent build - no cache available, building fresh..."
                docker buildx build --platform linux/amd64 \
                    --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:cache,mode=max" \
                    -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-outboundagent:${IMAGE_TAG}" . --push
            fi
        fi
        
        cd ..
        export HAS_OUTBOUNDAGENT=true
        log_success "Outbound agent image built and pushed!"
    else
        log_info "Skipping outbound agent build (BUILD_OUTBOUNDAGENT=false or directory not found)"
        export HAS_OUTBOUNDAGENT=false
    fi
    
    # Build Google Calendar MCP image if enabled and directory exists
    if [[ "${BUILD_GOOGLE_CALENDAR_MCP:-true}" == "true" ]] && [[ -d "google-calendar-mcp" ]]; then
        log_info "Building Google Calendar MCP image for AMD64 architecture..."
        
        cd google-calendar-mcp
        
        # Create Dockerfile if it doesn't exist
        if [[ ! -f "Dockerfile" ]]; then
            log_info "Creating Dockerfile for Google Calendar MCP..."
            create_google_calendar_mcp_dockerfile
        fi
        
        if [[ "$NO_CACHE" == "true" ]]; then
            log_info "Building Google Calendar MCP WITHOUT cache (--no-cache flag enabled)..."
            docker buildx build --platform linux/amd64 \
                --no-cache \
                -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:${IMAGE_TAG}" . --push
        else
            # Optimize for new projects - skip cache lookup on first build
            if docker manifest inspect "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:cache" >/dev/null 2>&1; then
                log_info "Using existing Google Calendar MCP cache for faster build..."
                docker buildx build --platform linux/amd64 \
                    --cache-from=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:cache" \
                    --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:cache,mode=max" \
                    -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:${IMAGE_TAG}" . --push
            else
                log_info "First Google Calendar MCP build - no cache available, building fresh..."
                docker buildx build --platform linux/amd64 \
                    --cache-to=type=registry,ref="${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:cache,mode=max" \
                    -t "${ACR_LOGIN_SERVER}/${PROJECT_NAME}-google-calendar-mcp:${IMAGE_TAG}" . --push
            fi
        fi
        
        cd ..
        export HAS_GOOGLE_CALENDAR_MCP=true
        log_success "Google Calendar MCP image built and pushed!"
    else
        log_info "Skipping Google Calendar MCP build (BUILD_GOOGLE_CALENDAR_MCP=false or directory not found)"
        export HAS_GOOGLE_CALENDAR_MCP=false
    fi
    
    log_success "Docker images built and pushed!"
}

# Create Dockerfile for outbound agent if it doesn't exist
create_agent_dockerfile() {
    cat > Dockerfile << 'EOF'
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    portaudio19-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN groupadd -r agent && useradd -r -g agent agent
RUN chown -R agent:agent /app && \
    mkdir -p /tmp /app/tmp && \
    chown -R agent:agent /tmp /app/tmp
USER agent

# Expose port for health checks
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the agent
CMD ["python", "agent.py", "start"]
EOF
}

# Create Dockerfile for Google Calendar MCP if it doesn't exist
create_google_calendar_mcp_dockerfile() {
    cat > Dockerfile << 'EOF'
FROM python:3.12-slim

# Install system dependencies including uv
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Copy project files
COPY . .

# Create virtual environment and install dependencies
RUN uv venv .venv
RUN . .venv/bin/activate && uv pip install -e .

# Create non-root user
RUN groupadd -r mcp && useradd -r -g mcp mcp
RUN chown -R mcp:mcp /app && \
    mkdir -p /tmp /app/tmp && \
    chown -R mcp:mcp /tmp /app/tmp
USER mcp

# Expose port for MCP server
EXPOSE 8000

# Health check endpoint (simple HTTP check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the MCP server
CMD ["/bin/bash", "-c", "source .venv/bin/activate && python server.py"]
EOF
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
    
    # Export deployment configuration from .env
    export PROJECT_PREFIX="${PROJECT_NAME}"
    export NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    
    # Export replica configuration
    export BACKEND_REPLICAS="${BACKEND_REPLICAS:-2}"
    export FRONTEND_REPLICAS="${FRONTEND_REPLICAS:-1}"
    export OUTBOUNDAGENT_REPLICAS="${OUTBOUNDAGENT_REPLICAS:-1}"
    export CELERY_WORKER_REPLICAS="${CELERY_WORKER_REPLICAS:-2}"
    export REDIS_REPLICAS="${REDIS_REPLICAS:-1}"
    
    # Export resource configuration
    export BACKEND_CPU_REQUEST="${BACKEND_CPU_REQUEST:-250m}"
    export BACKEND_CPU_LIMIT="${BACKEND_CPU_LIMIT:-1000m}"
    export BACKEND_MEMORY_REQUEST="${BACKEND_MEMORY_REQUEST:-512Mi}"
    export BACKEND_MEMORY_LIMIT="${BACKEND_MEMORY_LIMIT:-2Gi}"
    
    export FRONTEND_CPU_REQUEST="${FRONTEND_CPU_REQUEST:-100m}"
    export FRONTEND_CPU_LIMIT="${FRONTEND_CPU_LIMIT:-500m}"
    export FRONTEND_MEMORY_REQUEST="${FRONTEND_MEMORY_REQUEST:-128Mi}"
    export FRONTEND_MEMORY_LIMIT="${FRONTEND_MEMORY_LIMIT:-512Mi}"
    
    export OUTBOUNDAGENT_CPU_REQUEST="${OUTBOUNDAGENT_CPU_REQUEST:-500m}"
    export OUTBOUNDAGENT_CPU_LIMIT="${OUTBOUNDAGENT_CPU_LIMIT:-2000m}"
    export OUTBOUNDAGENT_MEMORY_REQUEST="${OUTBOUNDAGENT_MEMORY_REQUEST:-1Gi}"
    export OUTBOUNDAGENT_MEMORY_LIMIT="${OUTBOUNDAGENT_MEMORY_LIMIT:-4Gi}"
    
    export CELERY_CPU_REQUEST="${CELERY_CPU_REQUEST:-200m}"
    export CELERY_CPU_LIMIT="${CELERY_CPU_LIMIT:-800m}"
    export CELERY_MEMORY_REQUEST="${CELERY_MEMORY_REQUEST:-256Mi}"
    export CELERY_MEMORY_LIMIT="${CELERY_MEMORY_LIMIT:-1Gi}"
    
    export REDIS_CPU_REQUEST="${REDIS_CPU_REQUEST:-100m}"
    export REDIS_CPU_LIMIT="${REDIS_CPU_LIMIT:-500m}"
    export REDIS_MEMORY_REQUEST="${REDIS_MEMORY_REQUEST:-256Mi}"
    export REDIS_MEMORY_LIMIT="${REDIS_MEMORY_LIMIT:-1Gi}"
    
    # Google Calendar MCP Resources
    export GOOGLE_CALENDAR_MCP_CPU_REQUEST="${GOOGLE_CALENDAR_MCP_CPU_REQUEST:-100m}"
    export GOOGLE_CALENDAR_MCP_CPU_LIMIT="${GOOGLE_CALENDAR_MCP_CPU_LIMIT:-500m}"
    export GOOGLE_CALENDAR_MCP_MEMORY_REQUEST="${GOOGLE_CALENDAR_MCP_MEMORY_REQUEST:-256Mi}"
    export GOOGLE_CALENDAR_MCP_MEMORY_LIMIT="${GOOGLE_CALENDAR_MCP_MEMORY_LIMIT:-512Mi}"
    
    # Export HPA configuration
    export BACKEND_HPA_ENABLED="${BACKEND_HPA_ENABLED:-true}"
    export BACKEND_HPA_MIN_REPLICAS="${BACKEND_HPA_MIN_REPLICAS:-2}"
    export BACKEND_HPA_MAX_REPLICAS="${BACKEND_HPA_MAX_REPLICAS:-10}"
    export BACKEND_HPA_CPU_THRESHOLD="${BACKEND_HPA_CPU_THRESHOLD:-70}"
    export BACKEND_HPA_MEMORY_THRESHOLD="${BACKEND_HPA_MEMORY_THRESHOLD:-80}"
    
    export OUTBOUNDAGENT_HPA_ENABLED="${OUTBOUNDAGENT_HPA_ENABLED:-true}"
    export OUTBOUNDAGENT_HPA_MIN_REPLICAS="${OUTBOUNDAGENT_HPA_MIN_REPLICAS:-1}"
    export OUTBOUNDAGENT_HPA_MAX_REPLICAS="${OUTBOUNDAGENT_HPA_MAX_REPLICAS:-5}"
    export OUTBOUNDAGENT_HPA_CPU_THRESHOLD="${OUTBOUNDAGENT_HPA_CPU_THRESHOLD:-60}"
    export OUTBOUNDAGENT_HPA_MEMORY_THRESHOLD="${OUTBOUNDAGENT_HPA_MEMORY_THRESHOLD:-75}"
    
    export CELERY_HPA_ENABLED="${CELERY_HPA_ENABLED:-true}"
    export CELERY_HPA_MIN_REPLICAS="${CELERY_HPA_MIN_REPLICAS:-1}"
    export CELERY_HPA_MAX_REPLICAS="${CELERY_HPA_MAX_REPLICAS:-8}"
    export CELERY_HPA_CPU_THRESHOLD="${CELERY_HPA_CPU_THRESHOLD:-75}"
    
    # Export health check configuration (use .env values or fallback to existing logic)
    export BACKEND_LIVENESS_INITIAL_DELAY="${BACKEND_LIVENESS_INITIAL_DELAY:-$LIVENESS_INITIAL_DELAY}"
    export BACKEND_LIVENESS_PERIOD="${BACKEND_LIVENESS_PERIOD:-$HEALTH_CHECK_PERIOD}"
    export BACKEND_LIVENESS_TIMEOUT="${BACKEND_LIVENESS_TIMEOUT:-$HEALTH_TIMEOUT}"
    export BACKEND_LIVENESS_FAILURE_THRESHOLD="${BACKEND_LIVENESS_FAILURE_THRESHOLD:-$HEALTH_FAILURE_THRESHOLD}"
    
    export BACKEND_READINESS_INITIAL_DELAY="${BACKEND_READINESS_INITIAL_DELAY:-$READINESS_INITIAL_DELAY}"
    export BACKEND_READINESS_PERIOD="${BACKEND_READINESS_PERIOD:-$HEALTH_CHECK_PERIOD}"
    export BACKEND_READINESS_TIMEOUT="${BACKEND_READINESS_TIMEOUT:-$HEALTH_TIMEOUT}"
    export BACKEND_READINESS_FAILURE_THRESHOLD="${BACKEND_READINESS_FAILURE_THRESHOLD:-$HEALTH_FAILURE_THRESHOLD}"
    
    export OUTBOUNDAGENT_LIVENESS_INITIAL_DELAY="${OUTBOUNDAGENT_LIVENESS_INITIAL_DELAY:-$LIVENESS_INITIAL_DELAY}"
    export OUTBOUNDAGENT_LIVENESS_PERIOD="${OUTBOUNDAGENT_LIVENESS_PERIOD:-$HEALTH_CHECK_PERIOD}"
    export OUTBOUNDAGENT_READINESS_INITIAL_DELAY="${OUTBOUNDAGENT_READINESS_INITIAL_DELAY:-$READINESS_INITIAL_DELAY}"
    export OUTBOUNDAGENT_READINESS_PERIOD="${OUTBOUNDAGENT_READINESS_PERIOD:-$HEALTH_CHECK_PERIOD}"
    
    # Base64 encode outbound agent secrets for Kubernetes
    export LIVEKIT_URL_B64="$(echo -n "${LIVEKIT_URL}" | base64)"
    export LIVEKIT_API_KEY_B64="$(echo -n "${LIVEKIT_API_KEY}" | base64)"
    export LIVEKIT_API_SECRET_B64="$(echo -n "${LIVEKIT_API_SECRET}" | base64)"
    export OPENAI_API_KEY_B64="$(echo -n "${OPENAI_API_KEY}" | base64)"
    export DEEPGRAM_API_KEY_B64="$(echo -n "${DEEPGRAM_API_KEY}" | base64)"
    export ELEVEN_API_KEY_B64="$(echo -n "${ELEVEN_API_KEY}" | base64)"
    export MCP_SERVER_URL_B64="$(echo -n "${MCP_SERVER_URL:-}" | base64)"
    
    # Base64 encode Google Calendar MCP secrets for Kubernetes
    export DB_PASSWORD_B64="$(echo -n "${DB_PASSWORD}" | base64)"
    export DB_HOST_B64="$(echo -n "${DB_HOST}" | base64)"
    export DB_PORT_B64="$(echo -n "${DB_PORT:-5432}" | base64)"
    export DB_NAME_B64="$(echo -n "${DB_NAME}" | base64)"
    export DB_USER_B64="$(echo -n "${DB_USER}" | base64)"
    
    # LiveKit Agent Configuration: Managed via database (no setup needed)
    
    # Agent Configuration - Base64 encoded
    export AGENT_NAME_B64="$(echo -n "${AGENT_NAME:-hotcalls_agent}" | base64)"
    export NAME_B64="$(echo -n "${NAME:-hotcalls_agent}" | base64)"
    export RING_DURATION_B64="$(echo -n "${RING_DURATION:-2.0}" | base64)"
    export ENABLE_BACKGROUND_AUDIO_B64="$(echo -n "${ENABLE_BACKGROUND_AUDIO:-true}" | base64)"
    export OFFICE_AMBIENCE_VOLUME_B64="$(echo -n "${OFFICE_AMBIENCE_VOLUME:-0.08}" | base64)"
    export TYPING_SOUND_VOLUME_B64="$(echo -n "${TYPING_SOUND_VOLUME:-0.06}" | base64)"
    export SIP_PROVIDER_B64="$(echo -n "${SIP_PROVIDER:-}" | base64)"
    export TRUNK_ID_B64="$(echo -n "${TRUNK_ID:-}" | base64)"
    
    # Call Log Configuration - Base64 encoded
    export CALL_LOG_ENDPOINT_URL_B64="$(echo -n "${CALL_LOG_ENDPOINT_URL:-}" | base64)"
    export CALL_LOG_TIMEOUT_B64="$(echo -n "${CALL_LOG_TIMEOUT:-10.0}" | base64)"
    export CALL_LOG_MAX_RETRIES_B64="$(echo -n "${CALL_LOG_MAX_RETRIES:-3}" | base64)"
    export ELEVEN_VOICE_ID_B64="$(echo -n "${ELEVEN_VOICE_ID:-}" | base64)"
    
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
        # Set call log endpoint URL for staging/production
        export CALL_LOG_ENDPOINT_URL="${BASE_URL}/api/calls/call-logs/"
    else
        export BASE_URL="http://localhost:8000"
        # Set call log endpoint URL for development
        export CALL_LOG_ENDPOINT_URL="${BASE_URL}/api/calls/call-logs/"
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
    
    # Deploy outbound agent if available (parallel with services)
    if [[ "${HAS_OUTBOUNDAGENT:-false}" == "true" ]] && [[ -f "outboundagent-deployment.yaml" ]]; then
        log_info "Deploying outbound agent..."
        envsubst < outboundagent-configmap.yaml | kubectl apply -f - &
        envsubst < outboundagent-secrets.yaml | kubectl apply -f - &
        envsubst < outboundagent-deployment.yaml | kubectl apply -f - &
        envsubst < outboundagent-service.yaml | kubectl apply -f - &
    fi
    
    # Deploy Google Calendar MCP if available (parallel with services)
    if [[ "${HAS_GOOGLE_CALENDAR_MCP:-false}" == "true" ]] && [[ -f "google-calendar-mcp-deployment.yaml" ]]; then
        log_info "Deploying Google Calendar MCP..."
        envsubst < google-calendar-mcp-configmap.yaml | kubectl apply -f - &
        envsubst < google-calendar-mcp-secrets.yaml | kubectl apply -f - &
        envsubst < google-calendar-mcp-deployment.yaml | kubectl apply -f - &
        envsubst < google-calendar-mcp-service.yaml | kubectl apply -f - &
        envsubst < google-calendar-mcp-ingress.yaml | kubectl apply -f - &
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
    
    # Apply custom configuration for large file uploads
    log_info "Configuring nginx ingress controller for large file uploads..."
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
data:
  proxy-body-size: "1024m"
  client-body-buffer-size: "100m"
  proxy-connect-timeout: "600"
  proxy-send-timeout: "600"
  proxy-read-timeout: "600"
EOF
    
    # Restart the controller to pick up the new configuration
    log_info "Restarting nginx ingress controller to apply configuration..."
    kubectl rollout restart deployment/ingress-nginx-controller -n ingress-nginx || true
    
    # Wait for the rollout to complete
    kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=300s || true
}

# Show Direct Storage configuration (CDN removed)
show_storage_configuration() {
    echo ""
    log_success "🚀 STORAGE CONFIGURATION"
    echo ""
    
    log_success "📁 Direct Storage Domain: https://$AZURE_CUSTOM_DOMAIN"
    log_success "   • Voice Files: https://$AZURE_CUSTOM_DOMAIN/media/voice_samples/"
    log_success "   • Voice Pictures: https://$AZURE_CUSTOM_DOMAIN/media/voice_pictures/"
    echo ""
    log_info "✅ Direct Azure Storage - Fast and reliable!"
    log_info "   Your media files are served directly from Azure Storage."
    
    echo ""
    log_info "🎯 Direct Storage Benefits:"
    log_info "   • ⚡ Immediate availability"
    log_info "   • 🔒 HTTPS enabled by default"
    log_info "   • 💪 Simple and reliable"
    log_info "   • 🛠️ No caching issues"
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
        
        # Show Direct Storage configuration
        show_storage_configuration
        
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

# Show comprehensive deployment status and diagnostics
show_status() {
    NAMESPACE="${PROJECT_NAME}-${ENVIRONMENT}"
    
    echo
    echo "🔍 =============================================================================="
    log_success "📊 COMPREHENSIVE DEPLOYMENT DIAGNOSTICS"
    echo "🔍 =============================================================================="
    echo
    
    # 1. Pod Status Summary
    echo "📦 POD STATUS SUMMARY:"
    echo "────────────────────────────────────────────────────────────────────────────"
    kubectl get pods -n "$NAMESPACE" -o wide
    echo
    
    # 2. Outbound Agent Specific Diagnostics
    if kubectl get deployment "${PROJECT_NAME}-outboundagent" -n "$NAMESPACE" >/dev/null 2>&1; then
        echo "🤖 OUTBOUND AGENT DIAGNOSTICS:"
        echo "────────────────────────────────────────────────────────────────────────────"
        
        AGENT_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=outboundagent --no-headers -o custom-columns=":metadata.name" | head -1)
        
        if [[ -n "$AGENT_POD" ]]; then
            echo "   🟢 Agent Pod: $AGENT_POD"
            echo "   📊 Status: $(kubectl get pod "$AGENT_POD" -n "$NAMESPACE" --no-headers -o custom-columns=":status.phase")"
            echo "   🔄 Restarts: $(kubectl get pod "$AGENT_POD" -n "$NAMESPACE" --no-headers -o custom-columns=":status.containerStatuses[0].restartCount")"
            echo "   ⏰ Age: $(kubectl get pod "$AGENT_POD" -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.creationTimestamp")"
            echo "   📝 Recent Logs (last 10 lines):"
            echo "      ┌─────────────────────────────────────────────────────────────────"
            kubectl logs "$AGENT_POD" -n "$NAMESPACE" --tail=10 2>/dev/null | sed 's/^/      │ /'
            echo "      └─────────────────────────────────────────────────────────────────"
        else
            echo "   ❌ No outbound agent pod found!"
        fi
        echo
    fi
    
    # 3. Service Status
    echo "🌐 SERVICE STATUS:"
    echo "────────────────────────────────────────────────────────────────────────────"
    kubectl get services -n "$NAMESPACE" -o wide
    echo
    
    # 4. Ingress Status  
    echo "🔗 INGRESS STATUS:"
    echo "────────────────────────────────────────────────────────────────────────────"
    kubectl get ingress -n "$NAMESPACE" -o wide
    echo
    
    # 5. ConfigMap and Secrets Status
    echo "⚙️ CONFIGURATION STATUS:"
    echo "────────────────────────────────────────────────────────────────────────────"
    echo "   ConfigMaps:"
    kubectl get configmaps -n "$NAMESPACE" --no-headers | sed 's/^/   📄 /'
    echo "   Secrets:"
    kubectl get secrets -n "$NAMESPACE" --no-headers | sed 's/^/   🔐 /'
    echo
    
    # 6. HPA Status  
    echo "📈 HORIZONTAL POD AUTOSCALER STATUS:"
    echo "────────────────────────────────────────────────────────────────────────────"
    kubectl get hpa -n "$NAMESPACE" -o wide 2>/dev/null || echo "   ℹ️ No HPA configured"
    echo
    
    # 7. Recent Events
    echo "📢 RECENT EVENTS (last 10):"
    echo "────────────────────────────────────────────────────────────────────────────"
    kubectl get events -n "$NAMESPACE" --sort-by='.metadata.creationTimestamp' --no-headers | tail -10 | sed 's/^/   🔔 /'
    echo
    
    # 8. Detailed Component Health Checks
    echo "🩺 DETAILED COMPONENT HEALTH CHECKS:"
    echo "────────────────────────────────────────────────────────────────────────────"
    
    # Redis Health Check
    echo "   🔴 REDIS Health Check:"
    REDIS_POD=$(kubectl get pods -n "$NAMESPACE" -l app=redis --no-headers -o custom-columns=":metadata.name" | head -1)
    if [[ -n "$REDIS_POD" ]]; then
        if kubectl exec "$REDIS_POD" -n "$NAMESPACE" -- redis-cli ping 2>/dev/null | grep -q "PONG"; then
            echo "      ✅ Redis: RESPONDING to ping"
            # Check Redis memory usage
            REDIS_MEMORY=$(kubectl exec "$REDIS_POD" -n "$NAMESPACE" -- redis-cli info memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
            echo "      📊 Memory Usage: $REDIS_MEMORY"
        else
            echo "      ❌ Redis: NOT RESPONDING"
        fi
    else
        echo "      ❌ Redis: POD NOT FOUND"
    fi
    echo
    
    # Backend Health Check
    echo "   🖥️ BACKEND Health Check:"
    BACKEND_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=backend --no-headers -o custom-columns=":metadata.name" | head -1)
    if [[ -n "$BACKEND_POD" ]]; then
        # Check if backend is ready
        BACKEND_READY=$(kubectl get pod "$BACKEND_POD" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
        if [[ "$BACKEND_READY" == "True" ]]; then
            echo "      ✅ Backend Pod: READY"
            
            # Test health endpoint from inside the pod
            if kubectl exec "$BACKEND_POD" -n "$NAMESPACE" -- curl -s -f http://localhost:8000/health/ >/dev/null 2>&1; then
                echo "      ✅ Health endpoint: RESPONDING"
            else
                echo "      ❌ Health endpoint: NOT RESPONDING"
            fi
            
            # Test readiness endpoint
            if kubectl exec "$BACKEND_POD" -n "$NAMESPACE" -- curl -s -f http://localhost:8000/readiness/ >/dev/null 2>&1; then
                echo "      ✅ Readiness endpoint: RESPONDING"
            else
                echo "      ⚠️ Readiness endpoint: NOT RESPONDING"
            fi
        else
            echo "      ❌ Backend Pod: NOT READY"
        fi
    else
        echo "      ❌ Backend: POD NOT FOUND"
    fi
    echo
    
    # Database Health Check
    echo "   🗄️ DATABASE Health Check:"
    if [[ -n "$BACKEND_POD" ]]; then
        # Test database connection from backend pod
        DB_TEST=$(kubectl exec "$BACKEND_POD" -n "$NAMESPACE" -- python manage.py shell -c "
from django.db import connection
try:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        result = cursor.fetchone()
    print('DB_CONNECTION_OK' if result else 'DB_CONNECTION_FAILED')
except Exception as e:
    print(f'DB_CONNECTION_ERROR: {e}')
" 2>/dev/null)
        
        if echo "$DB_TEST" | grep -q "DB_CONNECTION_OK"; then
            echo "      ✅ Database: CONNECTION OK"
            
            # Check for pending migrations
            PENDING_MIGRATIONS=$(kubectl exec "$BACKEND_POD" -n "$NAMESPACE" -- python manage.py showmigrations --plan 2>/dev/null | grep "\\[ \\]" | wc -l)
            if [[ "$PENDING_MIGRATIONS" -eq 0 ]]; then
                echo "      ✅ Migrations: UP TO DATE"
            else
                echo "      ⚠️ Migrations: $PENDING_MIGRATIONS PENDING"
            fi
        else
            echo "      ❌ Database: CONNECTION FAILED"
            echo "      🔍 Error: $DB_TEST"
        fi
    else
        echo "      ❌ Cannot test DB: Backend pod not available"
    fi
    echo
    
    # Celery Workers Health Check
    echo "   👷 CELERY WORKERS Health Check:"
    CELERY_PODS=($(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=celery-worker --no-headers -o custom-columns=":metadata.name"))
    
    if [[ ${#CELERY_PODS[@]} -gt 0 ]]; then
        echo "      📊 Found ${#CELERY_PODS[@]} Celery worker pod(s)"
        
        for pod in "${CELERY_PODS[@]}"; do
            POD_READY=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
            if [[ "$POD_READY" == "True" ]]; then
                echo "      ✅ Worker $pod: READY"
                
                # Check if celery is actually running
                if kubectl exec "$pod" -n "$NAMESPACE" -- pgrep -f "celery worker" >/dev/null 2>&1; then
                    echo "      ✅ Worker $pod: PROCESS RUNNING"
                else
                    echo "      ❌ Worker $pod: PROCESS NOT FOUND"
                fi
            else
                echo "      ❌ Worker $pod: NOT READY"
            fi
        done
        
        # Check Celery status from one of the workers
        FIRST_CELERY_POD="${CELERY_PODS[0]}"
        echo "      🔍 Checking active workers via Celery inspect:"
        CELERY_STATUS=$(kubectl exec "$FIRST_CELERY_POD" -n "$NAMESPACE" -- celery -A hotcalls inspect active 2>/dev/null | grep -E "(OK|Error)" | head -5)
        if [[ -n "$CELERY_STATUS" ]]; then
            echo "$CELERY_STATUS" | sed 's/^/         /'
        else
            echo "         ⚠️ Could not retrieve Celery status"
        fi
    else
        echo "      ❌ Celery Workers: NO PODS FOUND"
    fi
    echo
    
    # Celery Beat Health Check
    echo "   ⏰ CELERY BEAT Health Check:"
    BEAT_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/component=celery-beat --no-headers -o custom-columns=":metadata.name" | head -1)
    if [[ -n "$BEAT_POD" ]]; then
        BEAT_READY=$(kubectl get pod "$BEAT_POD" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
        if [[ "$BEAT_READY" == "True" ]]; then
            echo "      ✅ Celery Beat: READY"
            
            if kubectl exec "$BEAT_POD" -n "$NAMESPACE" -- pgrep -f "celery beat" >/dev/null 2>&1; then
                echo "      ✅ Beat Scheduler: PROCESS RUNNING"
            else
                echo "      ❌ Beat Scheduler: PROCESS NOT FOUND"
            fi
        else
            echo "      ❌ Celery Beat: NOT READY"
        fi
    else
        echo "      ❌ Celery Beat: POD NOT FOUND"
    fi
    echo
    
    # External Endpoints Health Check
    echo "   🌐 EXTERNAL ENDPOINTS Health Check:"
    EXTERNAL_IP=$(kubectl get ingress "${PROJECT_NAME}-ingress" -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    if [[ -n "$EXTERNAL_IP" ]]; then
        echo "      🌍 External IP: $EXTERNAL_IP"
        
        # Test health endpoint
        HEALTH_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null "http://$EXTERNAL_IP/health/" 2>/dev/null)
        if [[ "$HEALTH_RESPONSE" == "200" ]]; then
            echo "      ✅ Health endpoint: RESPONDING (HTTP $HEALTH_RESPONSE)"
        else
            echo "      ❌ Health endpoint: NOT RESPONDING (HTTP $HEALTH_RESPONSE)"
        fi
        
        # Test API endpoint
        API_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null "http://$EXTERNAL_IP/api/" 2>/dev/null)
        if [[ "$API_RESPONSE" == "200" ]]; then
            echo "      ✅ API endpoint: ACCESSIBLE (HTTP $API_RESPONSE)"
        else
            echo "      ⚠️ API endpoint: NOT RESPONDING (HTTP $API_RESPONSE)"
        fi
        
        # Test frontend
        FRONTEND_RESPONSE=$(curl -s -w "%{http_code}" -o /dev/null "http://$EXTERNAL_IP/" 2>/dev/null)
        if [[ "$FRONTEND_RESPONSE" == "200" ]]; then
            echo "      ✅ Frontend: ACCESSIBLE (HTTP $FRONTEND_RESPONSE)"
        else
            echo "      ⚠️ Frontend: NOT RESPONDING (HTTP $FRONTEND_RESPONSE)"
        fi
    else
        echo "      ⏳ External IP: PENDING"
    fi
    echo
    
    # 9. Resource Usage Summary
    echo "📊 RESOURCE USAGE SUMMARY:"
    echo "────────────────────────────────────────────────────────────────────────────"
    kubectl top pods -n "$NAMESPACE" 2>/dev/null | sed 's/^/   📈 /' || echo "   ℹ️ Metrics not available (metrics-server required)"
    echo
    
    # 10. Quick Reference Commands
    echo "🛠️ USEFUL DIAGNOSTIC COMMANDS:"
    echo "────────────────────────────────────────────────────────────────────────────"
    echo "   🔍 Watch pods:           kubectl get pods -n $NAMESPACE -w"
    echo "   📝 Backend logs:         kubectl logs -f deployment/${PROJECT_NAME}-backend -n $NAMESPACE"
    echo "   🤖 Agent logs:           kubectl logs -f deployment/${PROJECT_NAME}-outboundagent -n $NAMESPACE"
    echo "   🌐 Check ingress:        kubectl describe ingress ${PROJECT_NAME}-ingress -n $NAMESPACE"
    echo "   🔧 Debug pod:            kubectl exec -it <pod-name> -n $NAMESPACE -- /bin/bash"
    echo "   📊 Resource usage:       kubectl top pods -n $NAMESPACE"
    echo "   🔄 Restart deployment:   kubectl rollout restart deployment/${PROJECT_NAME}-backend -n $NAMESPACE"
    echo
    
    echo "🔍 =============================================================================="
    log_success "📊 DIAGNOSTICS COMPLETE"
    echo "🔍 =============================================================================="
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
    clear
    # Set up trap to clean up on exit (success or failure)
    trap cleanup_on_exit EXIT
    
    # Mark that deployment has started
    DEPLOYMENT_STARTED=true
    
    log_info "Starting HotCalls deployment..."
    
    check_prerequisites
    load_environment
    
    # Display configuration after loading .env
    echo "🎯 Deployment Configuration:"
    echo "   PROJECT_NAME: $PROJECT_NAME"
    echo "   Environment: $ENVIRONMENT" 
    echo "   Location: $LOCATION_SHORT"
    echo "   Update Only: $UPDATE_ONLY"
    echo "   Docker Cache: $(if [[ "$NO_CACHE" == "true" ]]; then echo "Disabled (fresh build)"; else echo "Enabled"; fi)"
    echo "   Backend Branch: $BRANCH_BACKEND"
    echo "   Frontend Branch: $BRANCH_FRONTEND"
    echo "   Agent Branch: $BRANCH_AGENT"
    if [[ -n "${DOMAIN:-}" ]]; then
        echo "   Domain: $DOMAIN"
        echo "   HTTPS: Enabled"
    fi
    if [[ "$PURGE_DB" == "true" ]]; then
        echo "   🚨 PURGE MODE: ENABLED - ALL DATA WILL BE DELETED! 🚨"
    fi
    echo ""
    
    # Handle repository checkout and branch management
    checkout_and_pull_repositories
    
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