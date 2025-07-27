#!/bin/bash

# HotCalls Cleanup Script
# This script cleans up the deployed resources

set -euo pipefail

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
    else
        log_warning ".env file not found. Using default environment: staging"
        export ENVIRONMENT="staging"
    fi
}

# Clean up Kubernetes resources
cleanup_kubernetes() {
    log_info "Cleaning up Kubernetes resources..."
    
    local namespace="hotcalls-${ENVIRONMENT:-staging}"
    
    if kubectl get namespace "$namespace" >/dev/null 2>&1; then
        log_info "Deleting Kubernetes resources in namespace: $namespace"
        
        # Delete in reverse order of creation
        kubectl delete ingress --all -n "$namespace" --ignore-not-found=true
        kubectl delete hpa --all -n "$namespace" --ignore-not-found=true
        kubectl delete service --all -n "$namespace" --ignore-not-found=true
        kubectl delete deployment --all -n "$namespace" --ignore-not-found=true
        kubectl delete secret --all -n "$namespace" --ignore-not-found=true
        kubectl delete configmap --all -n "$namespace" --ignore-not-found=true
        kubectl delete serviceaccount --all -n "$namespace" --ignore-not-found=true
        kubectl delete rolebinding --all -n "$namespace" --ignore-not-found=true
        kubectl delete role --all -n "$namespace" --ignore-not-found=true
        
        # Delete namespace
        kubectl delete namespace "$namespace" --ignore-not-found=true
        
        log_success "Kubernetes resources cleaned up!"
    else
        log_info "Namespace $namespace does not exist. Nothing to clean up."
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
    read -p "Are you sure you want to destroy the Terraform infrastructure? (yes/no): " confirm
    
    if [[ "$confirm" == "yes" ]]; then
        log_info "Destroying Terraform infrastructure..."
        
        cd terraform
        
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
        
        terraform destroy -auto-approve
        
        cd ..
        
        log_success "Infrastructure destroyed!"
    else
        log_info "Infrastructure destruction cancelled."
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -k, --kubernetes-only    Clean up only Kubernetes resources"
    echo "  -i, --infrastructure     Clean up Terraform infrastructure (dangerous!)"
    echo "  -f, --frontend-only      Clean up only frontend files (frontend/, dist/)"
    echo "  -a, --all               Clean up both Kubernetes and infrastructure"
    echo "  -h, --help              Show this help message"
}

# Main execution
main() {
    load_environment
    
    case "${1:-}" in
        -k|--kubernetes-only)
            cleanup_kubernetes
            ;;
        -i|--infrastructure)
            cleanup_infrastructure
            ;;
        -f|--frontend-only)
            cleanup_frontend_files
            ;;
        -a|--all)
            cleanup_kubernetes
            cleanup_infrastructure
            ;;
        -h|--help)
            show_usage
            ;;
        "")
            log_info "No option specified. Use -h for help."
            log_info "Safe default: cleaning up only Kubernetes resources..."
            cleanup_kubernetes
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
    
    log_success "Cleanup completed!"
}

# Run main function
main "$@" 