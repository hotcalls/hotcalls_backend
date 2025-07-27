#!/bin/bash

# HotCalls Cleanup Script
# This script cleans up the deployed resources

set -euo pipefail

# Default values
PROJECT_NAME="hotcalls"
ENVIRONMENT="staging"
LOCATION_SHORT="ne"

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
        -k|--kubernetes-only)
            CLEANUP_MODE="kubernetes"
            shift
            ;;
        -i|--infrastructure)
            CLEANUP_MODE="infrastructure"
            shift
            ;;
        -f|--frontend-only)
            CLEANUP_MODE="frontend"
            shift
            ;;
        -a|--all)
            CLEANUP_MODE="all"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --project-name=NAME      Set project name (default: hotcalls)"
            echo "  --environment=ENV        Set environment (default: staging)"
            echo "  --location-short=LOC     Set location short name (default: ne)"
            echo "  -k, --kubernetes-only    Clean up only Kubernetes resources"
            echo "  -i, --infrastructure     Clean up Terraform infrastructure (dangerous!)"
            echo "  -f, --frontend-only      Clean up only frontend files (frontend/, dist/)"
            echo "  -a, --all               Clean up both Kubernetes and infrastructure"
            echo "  -h, --help              Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                          # Clean K8s for hotcalls-staging"
            echo "  $0 --project-name=rg-3 --environment=staging -k  # Clean K8s for rg-3-staging"
            echo "  $0 --project-name=rg-3 --environment=staging -a  # Clean everything for rg-3-staging"
            echo "  $0 --project-name=rg-3 --location-short=we -a     # Clean rg-3 in West Europe"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set default cleanup mode if not specified
CLEANUP_MODE="${CLEANUP_MODE:-kubernetes}"

echo "🧹 Cleanup Configuration:"
echo "   Project Name: $PROJECT_NAME"
echo "   Environment: $ENVIRONMENT"
echo "   Location: $LOCATION_SHORT"
echo "   Cleanup Mode: $CLEANUP_MODE"
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

# Load environment variables from .env
load_environment() {
    if [[ -f ".env" ]]; then
        log_info "Loading environment variables from .env..."
        set -a
        source .env
        set +a
        log_success "Environment variables loaded!"
    else
        log_warning ".env file not found. Using command line parameters only."
    fi
}

# Clean up Kubernetes resources
cleanup_kubernetes() {
    log_info "Cleaning up Kubernetes resources..."
    
    local namespace="${PROJECT_NAME}-${ENVIRONMENT}"
    local project_prefix="$PROJECT_NAME"
    
    log_info "Target namespace: $namespace"
    log_info "Project prefix: $project_prefix"
    
    # Check if namespace exists
    if kubectl get namespace "$namespace" >/dev/null 2>&1; then
        log_info "Deleting Kubernetes resources in namespace: $namespace"
        
        # Delete in reverse order of creation
        log_info "Deleting ingress..."
        kubectl delete ingress "${project_prefix}-ingress" -n "$namespace" --ignore-not-found=true
        
        log_info "Deleting HPA..."
        kubectl delete hpa "${project_prefix}-backend-hpa" -n "$namespace" --ignore-not-found=true
        kubectl delete hpa "${project_prefix}-celery-worker-hpa" -n "$namespace" --ignore-not-found=true
        
        log_info "Deleting services..."
        kubectl delete service "${project_prefix}-backend-service" -n "$namespace" --ignore-not-found=true
        kubectl delete service "${project_prefix}-backend-internal" -n "$namespace" --ignore-not-found=true
        kubectl delete service "${project_prefix}-frontend-service" -n "$namespace" --ignore-not-found=true
        kubectl delete service "redis" -n "$namespace" --ignore-not-found=true
        
        log_info "Deleting deployments..."
        kubectl delete deployment "${project_prefix}-backend" -n "$namespace" --ignore-not-found=true
        kubectl delete deployment "${project_prefix}-celery-worker" -n "$namespace" --ignore-not-found=true
        kubectl delete deployment "${project_prefix}-celery-beat" -n "$namespace" --ignore-not-found=true
        kubectl delete deployment "${project_prefix}-frontend" -n "$namespace" --ignore-not-found=true
        kubectl delete deployment "redis" -n "$namespace" --ignore-not-found=true
        
        log_info "Deleting secrets and configmaps..."
        kubectl delete secret "${project_prefix}-secrets" -n "$namespace" --ignore-not-found=true
        kubectl delete configmap "${project_prefix}-config" -n "$namespace" --ignore-not-found=true
        
        log_info "Deleting RBAC resources..."
        kubectl delete serviceaccount "${project_prefix}-sa" -n "$namespace" --ignore-not-found=true
        kubectl delete rolebinding "${project_prefix}-rolebinding" -n "$namespace" --ignore-not-found=true
        kubectl delete role "${project_prefix}-role" -n "$namespace" --ignore-not-found=true
        
        # Delete namespace
        log_info "Deleting namespace..."
        kubectl delete namespace "$namespace" --ignore-not-found=true
        
        log_success "Kubernetes resources cleaned up!"
    else
        log_info "Namespace $namespace does not exist. Nothing to clean up."
    fi
    
    # Also clean up any malformed namespaces (like "rg-3-")
    local malformed_namespace="${PROJECT_NAME}-"
    if kubectl get namespace "$malformed_namespace" >/dev/null 2>&1; then
        log_warning "Found malformed namespace: $malformed_namespace - deleting it"
        kubectl delete namespace "$malformed_namespace" --ignore-not-found=true
    fi
    
    # Clean up local frontend files
    cleanup_frontend_files
}

# Clean up frontend files
cleanup_frontend_files() {
    log_info "Cleaning up frontend files..."
    
    if [[ -d "frontend" ]]; then
        log_warning "Removing frontend/ directory..."
        rm -rf frontend/
    fi
    
    if [[ -d "dist" ]]; then
        log_warning "Removing dist/ directory..."
        rm -rf dist/
    fi
    
    log_success "Frontend files cleaned up!"
}

# Clean up Terraform infrastructure
cleanup_infrastructure() {
    log_warning "This will destroy ALL Azure infrastructure including databases!"
    log_warning "Project: $PROJECT_NAME, Environment: $ENVIRONMENT"
    
    read -p "Are you sure you want to destroy the Terraform infrastructure? (yes/no): " confirm
    
    if [[ "$confirm" == "yes" ]]; then
        log_info "Destroying Terraform infrastructure..."
        
        cd terraform
        
        # Select the correct workspace
        WORKSPACE_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
        log_info "Using Terraform workspace: $WORKSPACE_NAME"
        
        # Check if workspace exists
        if terraform workspace list | grep -q "\b$WORKSPACE_NAME\b"; then
            log_info "Selecting workspace: $WORKSPACE_NAME"
            terraform workspace select "$WORKSPACE_NAME"
            
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
            
            # Fix storage account naming (no hyphens allowed)
            STORAGE_PREFIX=$(echo "${PROJECT_NAME}${ENVIRONMENT}${LOCATION_SHORT}" | tr -d '-')
            export TF_VAR_storage_account_prefix="$STORAGE_PREFIX"
            
            # Set Terraform variables from .env if available
            if [[ -f "../.env" ]]; then
                source ../.env
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
            fi
            
            log_info "Destroying infrastructure..."
            terraform destroy -auto-approve
            
            # Switch back to default workspace and delete the project workspace
            log_info "Cleaning up workspace..."
            terraform workspace select default
            terraform workspace delete "$WORKSPACE_NAME"
            
            log_success "Infrastructure destroyed!"
        else
            log_warning "Terraform workspace '$WORKSPACE_NAME' not found. Nothing to destroy."
        fi
        
        cd ..
    else
        log_info "Infrastructure destruction cancelled."
    fi
}

# Main execution
main() {
    log_info "Starting cleanup process..."
    
    load_environment
    
    case "$CLEANUP_MODE" in
        kubernetes)
            cleanup_kubernetes
            ;;
        infrastructure)
            cleanup_infrastructure
            ;;
        frontend)
            cleanup_frontend_files
            ;;
        all)
            cleanup_kubernetes
            cleanup_infrastructure
            ;;
        *)
            log_error "Unknown cleanup mode: $CLEANUP_MODE"
            exit 1
            ;;
    esac
    
    log_success "Cleanup completed! 🎉"
}

# Run main function
main "$@" 