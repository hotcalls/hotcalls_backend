#!/bin/bash

# Terraform-based deployment script for HotCalls
# This script uses Infrastructure as Code to manage everything!

# Note: We handle errors manually for robust recovery

# Configuration
ENVIRONMENT=${1:-staging}
FORCE_ALL=${2:-false}
MAP_IP=false
BRANCH="staging"

# Parse arguments
for arg in "$@"; do
  case $arg in
    --force-all)
      FORCE_ALL="true"
      shift
      ;;
    --map-ip)
      MAP_IP=true
      shift
      ;;
    --branch=*)
      BRANCH="${arg#*=}"
      shift
      ;;
  esac
done

echo "🚀 Starting Terraform-based deployment..."
echo "📋 Configuration:"
echo "   Environment: $ENVIRONMENT"
echo "   Force recreate: $FORCE_ALL"
echo "   Map IP to BASE_URL: $MAP_IP"
echo "   Branch: $BRANCH"
echo ""

# Validation
if [ -z "$ENVIRONMENT" ]; then
  echo "❌ Environment is required!"
  echo "Usage: $0 <environment> [--force-all] [--map-ip] [--branch=<branch>]"
  exit 1
fi

# Function to perform robust cleanup with multiple fallback strategies
robust_cleanup() {
  echo "🗑️ Method 1: Standard Terraform destroy..."
  terraform destroy -auto-approve \
    -var-file="${ENVIRONMENT}.tfvars" \
    -var="postgres_admin_password=$DB_PASSWORD" \
    -var="django_secret_key=$SECRET_KEY" \
    -var="app_db_user=$DB_USER" \
    -var="app_db_password=$DB_PASSWORD" \
    -var="app_secret_key=$SECRET_KEY" \
    -var="app_redis_password=$REDIS_PASSWORD" \
    -var="app_debug=$DEBUG" \
    -var="app_cors_allow_all=$CORS_ALLOW_ALL_ORIGINS" \
    -var="app_email_host=$EMAIL_HOST" \
    -var="app_email_port=$EMAIL_PORT" \
    -var="app_email_use_tls=$EMAIL_USE_TLS" \
    -var="app_email_use_ssl=$EMAIL_USE_SSL" \
    -var="app_email_host_user=$EMAIL_HOST_USER" \
    -var="app_email_host_password=$EMAIL_HOST_PASSWORD" \
    -var="app_default_from_email=$DEFAULT_FROM_EMAIL" \
    -var="app_server_email=$SERVER_EMAIL" \
    -var="app_base_url=$BASE_URL" \
    -var="container_image_tag=$ENVIRONMENT"
  
  if [ $? -eq 0 ]; then
    echo "✅ Standard destroy successful!"
    return 0
  fi
  
  echo "⚠️ Standard destroy failed, trying Method 2: Dependency-order cleanup..."
  
  # Try destroying in reverse dependency order
  echo "🎯 Destroying Kubernetes resources first..."
  terraform destroy -auto-approve \
    -target="module.kubernetes" \
    -var-file="${ENVIRONMENT}.tfvars" \
    -var="postgres_admin_password=$DB_PASSWORD" \
    -var="django_secret_key=$SECRET_KEY" \
    -var="app_db_user=$DB_USER" \
    -var="app_db_password=$DB_PASSWORD" \
    -var="app_secret_key=$SECRET_KEY" \
    -var="app_redis_password=$REDIS_PASSWORD" \
    -var="app_debug=$DEBUG" \
    -var="app_cors_allow_all=$CORS_ALLOW_ALL_ORIGINS" \
    -var="app_email_host=$EMAIL_HOST" \
    -var="app_email_port=$EMAIL_PORT" \
    -var="app_email_use_tls=$EMAIL_USE_TLS" \
    -var="app_email_use_ssl=$EMAIL_USE_SSL" \
    -var="app_email_host_user=$EMAIL_HOST_USER" \
    -var="app_email_host_password=$EMAIL_HOST_PASSWORD" \
    -var="app_default_from_email=$DEFAULT_FROM_EMAIL" \
    -var="app_server_email=$SERVER_EMAIL" \
    -var="app_base_url=$BASE_URL" \
    -var="container_image_tag=$ENVIRONMENT" 2>/dev/null || true
  
  echo "🎯 Destroying AKS cluster..."
  terraform destroy -auto-approve \
    -target="module.aks" \
    -var-file="${ENVIRONMENT}.tfvars" \
    -var="postgres_admin_password=$DB_PASSWORD" \
    -var="django_secret_key=$SECRET_KEY" \
    -var="app_db_user=$DB_USER" \
    -var="app_db_password=$DB_PASSWORD" \
    -var="app_secret_key=$SECRET_KEY" \
    -var="app_redis_password=$REDIS_PASSWORD" \
    -var="app_debug=$DEBUG" \
    -var="app_cors_allow_all=$CORS_ALLOW_ALL_ORIGINS" \
    -var="app_email_host=$EMAIL_HOST" \
    -var="app_email_port=$EMAIL_PORT" \
    -var="app_email_use_tls=$EMAIL_USE_TLS" \
    -var="app_email_use_ssl=$EMAIL_USE_SSL" \
    -var="app_email_host_user=$EMAIL_HOST_USER" \
    -var="app_email_host_password=$EMAIL_HOST_PASSWORD" \
    -var="app_default_from_email=$DEFAULT_FROM_EMAIL" \
    -var="app_server_email=$SERVER_EMAIL" \
    -var="app_base_url=$BASE_URL" \
    -var="container_image_tag=$ENVIRONMENT" 2>/dev/null || true
  
  # Wait for Azure to process deletions
  echo "⏳ Waiting 60s for Azure to process deletions..."
  sleep 60
  
  # Try full destroy again
  echo "🗑️ Method 3: Retry full destroy after dependency cleanup..."
  terraform destroy -auto-approve \
    -var-file="${ENVIRONMENT}.tfvars" \
    -var="postgres_admin_password=$DB_PASSWORD" \
    -var="django_secret_key=$SECRET_KEY" \
    -var="app_db_user=$DB_USER" \
    -var="app_db_password=$DB_PASSWORD" \
    -var="app_secret_key=$SECRET_KEY" \
    -var="app_redis_password=$REDIS_PASSWORD" \
    -var="app_debug=$DEBUG" \
    -var="app_cors_allow_all=$CORS_ALLOW_ALL_ORIGINS" \
    -var="app_email_host=$EMAIL_HOST" \
    -var="app_email_port=$EMAIL_PORT" \
    -var="app_email_use_tls=$EMAIL_USE_TLS" \
    -var="app_email_use_ssl=$EMAIL_USE_SSL" \
    -var="app_email_host_user=$EMAIL_HOST_USER" \
    -var="app_email_host_password=$EMAIL_HOST_PASSWORD" \
    -var="app_default_from_email=$DEFAULT_FROM_EMAIL" \
    -var="app_server_email=$SERVER_EMAIL" \
    -var="app_base_url=$BASE_URL" \
    -var="container_image_tag=$ENVIRONMENT"
  
  if [ $? -eq 0 ]; then
    echo "✅ Retry destroy successful!"
    return 0
  fi
  
  # Nuclear option: Delete entire resource group
  echo "🚨 Method 4: NUCLEAR OPTION - Resource Group deletion..."
  
  # Try to get RG name from Terraform state first
  RG_NAME=$(terraform show -json 2>/dev/null | grep -o '"resource_group_name":"[^"]*"' | cut -d'"' -f4 | head -1)
  
  # Fallback to constructed name
  if [ -z "$RG_NAME" ]; then
    RG_NAME="hotcalls-${ENVIRONMENT}-ne-rg"
  fi
  
  echo "💣 Deleting entire resource group: $RG_NAME"
  echo "⚠️ This will forcefully delete ALL resources!"
  
  # Force delete the resource group
  az group delete --name "$RG_NAME" --yes --no-wait 2>/dev/null || true
  
  # Clean up Terraform state files
  echo "🧹 Cleaning Terraform state..."
  rm -f terraform.tfstate terraform.tfstate.backup .terraform.lock.hcl 2>/dev/null || true
  rm -rf .terraform/ 2>/dev/null || true
  
  echo "⏳ Waiting for resource group deletion (max 10 minutes)..."
  
  # Wait for RG to be deleted with timeout
  for i in {1..20}; do
    if ! az group show --name "$RG_NAME" &>/dev/null; then
      echo "✅ Resource group successfully deleted!"
      return 0
    fi
    echo "⏳ Still deleting... (attempt $i/20) - This can take several minutes"
    sleep 30
  done
  
  echo "⚠️ Resource group deletion taking longer than expected"
  echo "🔄 Continuing with deployment - Azure will complete deletion in background"
  return 0
}

# Function for robust terraform apply with retries
robust_terraform_apply() {
  local description="$1"
  local targets="$2"
  local max_attempts=3
  
  echo "🏗️ $description..."
  
  for attempt in $(seq 1 $max_attempts); do
    echo "⏳ Attempt $attempt/$max_attempts..."
    
    if [ -n "$targets" ]; then
      terraform apply -auto-approve \
        $targets \
        -var-file="${ENVIRONMENT}.tfvars" \
        -var="postgres_admin_password=$DB_PASSWORD" \
        -var="django_secret_key=$SECRET_KEY" \
        -var="app_db_user=$DB_USER" \
        -var="app_db_password=$DB_PASSWORD" \
        -var="app_secret_key=$SECRET_KEY" \
        -var="app_redis_password=$REDIS_PASSWORD" \
        -var="app_debug=$DEBUG" \
        -var="app_cors_allow_all=$CORS_ALLOW_ALL_ORIGINS" \
        -var="app_email_host=$EMAIL_HOST" \
        -var="app_email_port=$EMAIL_PORT" \
        -var="app_email_use_tls=$EMAIL_USE_TLS" \
        -var="app_email_use_ssl=$EMAIL_USE_SSL" \
        -var="app_email_host_user=$EMAIL_HOST_USER" \
        -var="app_email_host_password=$EMAIL_HOST_PASSWORD" \
        -var="app_default_from_email=$DEFAULT_FROM_EMAIL" \
        -var="app_server_email=$SERVER_EMAIL" \
        -var="app_base_url=$BASE_URL" \
        -var="container_image_tag=$ENVIRONMENT"
    else
      terraform apply -auto-approve \
        -var-file="${ENVIRONMENT}.tfvars" \
        -var="postgres_admin_password=$DB_PASSWORD" \
        -var="django_secret_key=$SECRET_KEY" \
        -var="app_db_user=$DB_USER" \
        -var="app_db_password=$DB_PASSWORD" \
        -var="app_secret_key=$SECRET_KEY" \
        -var="app_redis_password=$REDIS_PASSWORD" \
        -var="app_debug=$DEBUG" \
        -var="app_cors_allow_all=$CORS_ALLOW_ALL_ORIGINS" \
        -var="app_email_host=$EMAIL_HOST" \
        -var="app_email_port=$EMAIL_PORT" \
        -var="app_email_use_tls=$EMAIL_USE_TLS" \
        -var="app_email_use_ssl=$EMAIL_USE_SSL" \
        -var="app_email_host_user=$EMAIL_HOST_USER" \
        -var="app_email_host_password=$EMAIL_HOST_PASSWORD" \
        -var="app_default_from_email=$DEFAULT_FROM_EMAIL" \
        -var="app_server_email=$SERVER_EMAIL" \
        -var="app_base_url=$BASE_URL" \
        -var="container_image_tag=$ENVIRONMENT"
    fi
    
    if [ $? -eq 0 ]; then
      echo "✅ $description completed successfully!"
      return 0
    fi
    
    if [ $attempt -lt $max_attempts ]; then
      echo "⚠️ Attempt $attempt failed, retrying in 30 seconds..."
      sleep 30
    fi
  done
  
  echo "❌ $description failed after $max_attempts attempts!"
  echo "🔄 You can try running the script again or check Azure portal for issues"
  return 1
}

# Function for robust Docker operations
robust_docker_operation() {
  local description="$1"
  local command="$2"
  local max_attempts=3
  
  echo "🐳 $description..."
  
  for attempt in $(seq 1 $max_attempts); do
    echo "⏳ Attempt $attempt/$max_attempts..."
    
    eval "$command"
    
    if [ $? -eq 0 ]; then
      echo "✅ $description completed successfully!"
      return 0
    fi
    
    if [ $attempt -lt $max_attempts ]; then
      echo "⚠️ Attempt $attempt failed, retrying in 15 seconds..."
      sleep 15
    fi
  done
  
  echo "❌ $description failed after $max_attempts attempts!"
  echo "🔄 You can try running the script again"
  return 1
}

# Load environment variables from .env file
echo "📋 Loading configuration from .env..."
if [ -f .env ]; then
  # Source the .env file
  source .env
  echo "✅ Configuration loaded from .env"
else
  echo "❌ .env file not found!"
  exit 1
fi

# Switch to correct branch and pull latest changes
echo "🔄 Switching to $BRANCH branch and pulling latest changes..."
git checkout $BRANCH 2>/dev/null || git checkout -b $BRANCH
git pull origin $BRANCH 2>/dev/null || echo "⚠️ Could not pull from origin (might be new branch)"

# Handle frontend repository
echo "🔄 Managing frontend repository..."
cd ../hotcalls-visual-prototype
git checkout $BRANCH 2>/dev/null || git checkout -b $BRANCH
git pull origin $BRANCH 2>/dev/null || echo "⚠️ Could not pull frontend from origin"
cd ../hotcalls

# Set BASE_URL dynamically if --map-ip is specified
if [ "$MAP_IP" = true ]; then
  echo "🔧 BASE_URL will be updated after getting external IP"
fi

# Initialize Terraform
echo "🔧 Initializing Terraform..."
cd terraform
terraform init

# Create or switch to workspace
echo "📁 Managing Terraform workspace: $ENVIRONMENT"
terraform workspace select $ENVIRONMENT 2>/dev/null || terraform workspace new $ENVIRONMENT

# Handle infrastructure recreation
if [ "$FORCE_ALL" = "true" ]; then
  echo "💥 Force recreating infrastructure..."
  echo "⚠️ This will destroy and recreate all resources!"
  read -p "Are you sure? (y/N): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    
    # Execute robust cleanup
    echo "🔧 Starting robust cleanup process..."
    if robust_cleanup; then
      echo "✅ Infrastructure cleanup completed successfully!"
    else
      echo "⚠️ Cleanup had some issues but continuing with deployment..."
      echo "🔄 Fresh deployment should work even if cleanup wasn't perfect"
    fi
    
  else
    echo "❌ Deployment cancelled"
    exit 1
  fi
fi

# Phase 1: Deploy infrastructure only (no Kubernetes resources)
echo "🏗️ Phase 1: Deploying infrastructure (AKS, ACR, PostgreSQL, etc.)..."
if ! robust_terraform_apply "Creating infrastructure without Kubernetes resources" "-target=module.acr -target=module.aks -target=module.postgres -target=module.storage -target=module.network -target=module.keyvault -target=module.monitoring"; then
  echo "❌ Failed to deploy infrastructure after multiple attempts!"
  echo "🔍 Check the error messages above for details"
  exit 1
fi

# Configure kubectl credentials before deploying Kubernetes resources
echo "🔧 Configuring kubectl credentials..."
RESOURCE_GROUP=$(terraform output -raw resource_group_name 2>/dev/null)
AKS_CLUSTER=$(terraform output -raw aks_cluster_name 2>/dev/null)

if [ -z "$RESOURCE_GROUP" ] || [ -z "$AKS_CLUSTER" ]; then
  echo "❌ Failed to get resource group or AKS cluster name from Terraform outputs!"
  exit 1
fi

echo "📋 Resource Group: $RESOURCE_GROUP"
echo "📋 AKS Cluster: $AKS_CLUSTER"

if ! robust_docker_operation "Configuring kubectl" "az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER --admin --overwrite-existing"; then
  echo "❌ Failed to configure kubectl after multiple attempts!"
  exit 1
fi

  # Get ACR details after infrastructure is created
  echo "📋 Getting ACR login server..."
  ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server 2>/dev/null)
  if [ -z "$ACR_LOGIN_SERVER" ]; then
    echo "❌ Failed to get ACR login server from Terraform outputs"
    echo "🔍 This usually means the ACR wasn't created properly"
    exit 1
  fi
  echo "📋 ACR Login Server: $ACR_LOGIN_SERVER"
  
  cd ..
  
  # Login to ACR with retries
  echo "🔐 Logging into ACR..."
  if ! robust_docker_operation "ACR Login" "az acr login --name \$(echo \$ACR_LOGIN_SERVER | cut -d'.' -f1)"; then
    echo "❌ Failed to login to ACR after multiple attempts!"
    exit 1
  fi
  
  # Build and push backend image
  if ! robust_docker_operation "Building backend image" "docker build --no-cache -t ${ACR_LOGIN_SERVER}/hotcalls-backend:${ENVIRONMENT} ."; then
    echo "❌ Failed to build backend image after multiple attempts!"
    exit 1
  fi
  
  if ! robust_docker_operation "Pushing backend image" "docker push ${ACR_LOGIN_SERVER}/hotcalls-backend:${ENVIRONMENT}"; then
    echo "❌ Failed to push backend image after multiple attempts!"
    exit 1
  fi
  
  # Build and push frontend image
  cd ../hotcalls-visual-prototype
  if ! robust_docker_operation "Building frontend image" "docker build --no-cache -f ../hotcalls/frontend-deploy/Dockerfile -t ${ACR_LOGIN_SERVER}/hotcalls-frontend:${ENVIRONMENT} ."; then
    echo "❌ Failed to build frontend image after multiple attempts!"
    exit 1
  fi
  
  if ! robust_docker_operation "Pushing frontend image" "docker push ${ACR_LOGIN_SERVER}/hotcalls-frontend:${ENVIRONMENT}"; then
    echo "❌ Failed to push frontend image after multiple attempts!"
    exit 1
  fi
  cd ../hotcalls
  
  # Phase 2: Deploy Kubernetes resources now that images are ready
  echo "🚀 Phase 2: Deploying Kubernetes resources with new Docker images..."
  cd terraform
  
  if ! robust_terraform_apply "Deploying Kubernetes resources" ""; then
    echo "❌ Failed to deploy Kubernetes resources after multiple attempts!"
    echo "🔍 Check the error messages above for details"  
    exit 1
  fi

echo ""
echo "✅ Deployment completed successfully!"

# Get outputs
NAMESPACE=$(terraform output -raw kubernetes_namespace)
EXTERNAL_IP=""

# Wait for external IP (kubectl already configured in Phase 1)
echo "⏳ Waiting for external IP..."
for i in {1..30}; do
  EXTERNAL_IP=$(kubectl get ingress -n $NAMESPACE -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
  if [ -n "$EXTERNAL_IP" ]; then
    break
  fi
  echo "Waiting for external IP... ($i/30)"
  sleep 10
done

# Update BASE_URL if --map-ip flag is set and external IP is available
if [ "$MAP_IP" = true ] && [ -n "$EXTERNAL_IP" ]; then
  echo "🔧 Updating BASE_URL to use external IP: $EXTERNAL_IP"
  kubectl patch secret hotcalls-secrets -n $NAMESPACE --type='json' -p='[{"op": "replace", "path": "/data/BASE_URL", "value":"'$(echo "http://$EXTERNAL_IP" | base64)'"}]'
  
  # Restart backend to pick up new BASE_URL
  kubectl rollout restart deployment/hotcalls-backend -n $NAMESPACE
  echo "🔄 Backend restarted to pick up new BASE_URL"
fi

# Run Django migrations
echo "🗄️ Running Django migrations..."
kubectl exec -n $NAMESPACE deployment/hotcalls-backend -- python manage.py migrate

cd ..

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📊 Summary:"
echo "  🌐 Namespace: $NAMESPACE"
if [ -n "$EXTERNAL_IP" ]; then
  echo "  🌍 External IP: $EXTERNAL_IP"
  echo "  🔗 Access your app at: http://$EXTERNAL_IP/"
else
  echo "  ⏳ External IP not yet available"
fi
echo ""
echo "🔍 Useful commands:"
echo "  View pods: kubectl get pods -n $NAMESPACE"
echo "  View services: kubectl get svc -n $NAMESPACE"
echo "  View logs: kubectl logs -f deployment/hotcalls-backend -n $NAMESPACE"
echo "" 