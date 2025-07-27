#!/bin/bash

# HotCalls Single-Stage Deployment Script
# This script deploys the entire application stack to Azure using Terraform and Kubernetes

set -euo pipefail

# Default values
PROJECT_NAME="hotcalls"
ENVIRONMENT="staging"
LOCATION_SHORT="we"

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
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --project-name=NAME    Set project name (default: hotcalls)"
            echo "                         Resource group will be: NAME-ENVIRONMENT-LOCATION-rg"
            echo "  --environment=ENV      Set environment (default: staging)"
            echo "  --location-short=LOC   Set location short name (default: we)"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                          # Deploy to hotcalls-staging-we-rg"
            echo "  $0 --project-name=rg-2                     # Deploy to rg-2-staging-we-rg"  
            echo "  $0 --project-name=myapp --environment=prod # Deploy to myapp-prod-we-rg"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🎯 Deployment Configuration:"
echo "   Project Name: $PROJECT_NAME"
echo "   Environment: $ENVIRONMENT" 
echo "   Location: $LOCATION_SHORT"
echo "   Resource Group: $PROJECT_NAME-$ENVIRONMENT-$LOCATION_SHORT-rg"
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
        
        log_success "Frontend repository cloned!"
    else
        log_info "Frontend directory exists. Updating..."
        cd frontend
        git pull origin main || git pull origin master
        cd ..
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

# Deploy infrastructure with Terraform
deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd terraform
    
    # Set Terraform variables from command line and .env
    export TF_VAR_project_name="$PROJECT_NAME"
    export TF_VAR_environment="$ENVIRONMENT"
    export TF_VAR_location_short="$LOCATION_SHORT"
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
    
    log_info "Planning Terraform deployment..."
    terraform plan -out=tfplan
    
    log_info "Applying Terraform deployment..."
    terraform apply tfplan
    
    log_success "Infrastructure deployed successfully!"
    
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
    
    # Build backend image
    log_info "Building backend image..."
    docker build -t "${ACR_LOGIN_SERVER}/hotcalls-backend:${IMAGE_TAG}" .
    
    log_info "Pushing backend image..."
    docker push "${ACR_LOGIN_SERVER}/hotcalls-backend:${IMAGE_TAG}"
    
    # Build frontend image if dist directory exists
    if [[ -d "dist" ]]; then
        log_info "Building frontend image..."
        docker build -f frontend-deploy/Dockerfile -t "${ACR_LOGIN_SERVER}/hotcalls-frontend:${IMAGE_TAG}" .
        
        log_info "Pushing frontend image..."
        docker push "${ACR_LOGIN_SERVER}/hotcalls-frontend:${IMAGE_TAG}"
        
        export HAS_FRONTEND=true
    else
        log_warning "No dist/ directory found, skipping frontend image build"
        export HAS_FRONTEND=false
    fi
    
    log_success "Docker images built and pushed!"
}

# Deploy Kubernetes resources
deploy_kubernetes() {
    log_info "Deploying Kubernetes resources..."
    
    cd k8s
    
    # Set environment variables for K8s manifests
    # ENVIRONMENT is already set from command line arguments
    export REPLICAS="${REPLICAS:-1}"
    
    # Apply manifests in order with environment substitution
    log_info "Creating namespace..."
    envsubst < namespace.yaml | kubectl apply -f -
    
    log_info "Creating RBAC resources..."
    envsubst < rbac.yaml | kubectl apply -f -
    
    log_info "Creating ConfigMap..."
    envsubst < configmap.yaml | kubectl apply -f -
    
    log_info "Creating Secrets..."
    envsubst < secrets.yaml | kubectl apply -f -
    
    log_info "Deploying Redis..."
    envsubst < redis-deployment.yaml | kubectl apply -f -
    
    log_info "Deploying backend..."
    envsubst < deployment.yaml | kubectl apply -f -
    
    log_info "Creating backend service..."
    envsubst < service.yaml | kubectl apply -f -
    
    # Deploy frontend only if we have it
    if [[ "${HAS_FRONTEND:-false}" == "true" ]] && [[ -f "frontend-deployment.yaml" ]]; then
        log_info "Deploying frontend..."
        envsubst < frontend-deployment.yaml | kubectl apply -f -
        
        log_info "Creating frontend service..."
        envsubst < frontend-service.yaml | kubectl apply -f -
    else
        log_info "Skipping frontend deployment (no frontend available)"
    fi
    
    log_info "Creating ingress..."
    envsubst < ingress.yaml | kubectl apply -f -
    
    log_info "Creating HPA..."
    envsubst < hpa.yaml | kubectl apply -f -
    
    log_success "Kubernetes resources deployed!"
    
    cd ..
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
    
    # Wait for backend deployment
    kubectl wait --for=condition=available deployment/hotcalls-backend \
        -n "hotcalls-${ENVIRONMENT}" --timeout=600s
    
    log_info "Waiting for ingress to get external IP..."
    
    # Wait for external IP (up to 10 minutes)
    for i in {1..60}; do
        EXTERNAL_IP=$(kubectl get ingress hotcalls-ingress -n "hotcalls-${ENVIRONMENT}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        
        if [[ -n "$EXTERNAL_IP" ]]; then
            break
        fi
        
        if [[ $i -eq 60 ]]; then
            log_warning "Ingress IP not ready after 10 minutes. Check status manually."
            kubectl get ingress -n "hotcalls-${ENVIRONMENT}"
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
        kubectl patch secret hotcalls-secrets -n "hotcalls-${ENVIRONMENT}" \
            --type='json' -p="[{'op': 'replace', 'path': '/data/BASE_URL', 'value': '$(echo -n "http://$EXTERNAL_IP" | base64)'}]"
        
        # Restart deployment to pick up new BASE_URL
        kubectl rollout restart deployment/hotcalls-backend -n "hotcalls-${ENVIRONMENT}"
    fi
}

# Show deployment status
show_status() {
    log_info "Deployment Status:"
    echo
    kubectl get all -n "hotcalls-${ENVIRONMENT}"
    echo
    log_info "Ingress Status:"
    kubectl get ingress -n "hotcalls-${ENVIRONMENT}"
    echo
    log_info "To check logs: kubectl logs -f deployment/hotcalls-backend -n hotcalls-${ENVIRONMENT}"
    log_info "To check ingress: kubectl get ingress -n hotcalls-${ENVIRONMENT}"
    log_info "To check nginx controller: kubectl get service -n ingress-nginx ingress-nginx-controller"
}

# Main execution
main() {
    log_info "Starting HotCalls deployment..."
    
    check_prerequisites
    load_environment
    check_azure_login
    setup_frontend
    deploy_infrastructure
    get_infrastructure_outputs
    configure_kubectl
    install_ingress_controller
    build_and_push_images
    deploy_kubernetes
    wait_for_deployment
    show_status
    
    log_success "Deployment completed successfully! 🚀"
}

# Run main function
main "$@" 