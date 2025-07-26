#!/bin/bash

# Hotcalls Staging Environment Redeployment Script
# This script will:
# 1. Destroy the old development environment
# 2. Create a new staging environment
# 3. Deploy backend and frontend to Kubernetes

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_section() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

# Check if user is sure
echo -e "${YELLOW}WARNING: This will destroy the current development environment and create a new staging environment.${NC}"
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    print_error "Redeployment cancelled."
    exit 1
fi

# Step 1: Delete current Kubernetes resources
print_section "Step 1: Cleaning up Kubernetes Resources"

print_status "Deleting hotcalls-dev namespace..."
kubectl delete namespace hotcalls-dev --ignore-not-found=true || true

print_status "Waiting for namespace deletion to complete..."
kubectl wait --for=delete namespace/hotcalls-dev --timeout=120s 2>/dev/null || true

# Step 2: Destroy Terraform resources
print_section "Step 2: Destroying Current Terraform Resources"

cd terraform

print_status "Initializing Terraform..."
terraform init

print_status "Destroying development resources..."
terraform destroy -auto-approve -var-file="terraform.tfvars"

# Step 3: Deploy new staging environment
print_section "Step 3: Deploying Staging Environment with Terraform"

print_status "Planning Terraform deployment..."
terraform plan -var-file="staging.tfvars" -out=tfplan

print_status "Applying Terraform configuration..."
terraform apply -auto-approve tfplan

# Get outputs for later use
print_status "Getting Terraform outputs..."
export ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
export AKS_CLUSTER_NAME=$(terraform output -raw aks_cluster_name)
export RESOURCE_GROUP=$(terraform output -raw resource_group_name)
export POSTGRES_FQDN=$(terraform output -raw postgres_fqdn)
export POSTGRES_DB_NAME=$(terraform output -raw postgres_database_name)
export POSTGRES_ADMIN_USER=$(terraform output -raw postgres_admin_username)
export STORAGE_ACCOUNT=$(terraform output -raw storage_account_name)
export KEY_VAULT_URI=$(terraform output -raw key_vault_uri)

# Get storage account key
export STORAGE_KEY=$(az storage account keys list -n $STORAGE_ACCOUNT -g $RESOURCE_GROUP --query "[0].value" -o tsv)

# Step 4: Configure kubectl for new AKS cluster
print_section "Step 4: Configuring Kubernetes Access"

print_status "Getting AKS credentials..."
az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER_NAME --overwrite-existing

# Step 5: Create Kubernetes namespace and secrets
print_section "Step 5: Setting up Kubernetes Resources"

print_status "Creating staging namespace..."
kubectl create namespace hotcalls-staging

print_status "Creating secrets..."
kubectl create secret generic hotcalls-secrets -n hotcalls-staging \
  --from-literal=SECRET_KEY="$(openssl rand -base64 32)" \
  --from-literal=ALLOWED_HOSTS="localhost,127.0.0.1,app1.hotcalls.ai" \
  --from-literal=DB_NAME="$POSTGRES_DB_NAME" \
  --from-literal=DB_USER="$POSTGRES_ADMIN_USER" \
  --from-literal=DB_PASSWORD="ChangeMe123!" \
  --from-literal=DB_HOST="$POSTGRES_FQDN" \
  --from-literal=REDIS_HOST="redis-service" \
  --from-literal=REDIS_PORT="6379" \
  --from-literal=REDIS_DB="0" \
  --from-literal=REDIS_PASSWORD="" \
  --from-literal=CELERY_BROKER_URL="redis://redis-service:6379/0" \
  --from-literal=CELERY_RESULT_BACKEND="redis://redis-service:6379/0" \
  --from-literal=AZURE_ACCOUNT_NAME="$STORAGE_ACCOUNT" \
  --from-literal=AZURE_STORAGE_KEY="$STORAGE_KEY" \
  --from-literal=AZURE_CUSTOM_DOMAIN="" \
  --from-literal=AZURE_KEY_VAULT_URL="$KEY_VAULT_URI" \
  --from-literal=AZURE_CLIENT_ID="" \
  --from-literal=AZURE_MONITOR_CONNECTION_STRING="" \
  --from-literal=CORS_ALLOWED_ORIGINS="https://app1.hotcalls.ai" \
  --from-literal=BASE_URL="https://app1.hotcalls.ai"

# Step 6: Deploy Redis (needed for backend)
print_section "Step 6: Deploying Redis"

cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: hotcalls-staging
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: hotcalls-staging
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
EOF

# Step 7: Build and deploy backend
print_section "Step 7: Building and Deploying Backend"

cd ..

print_status "Building backend Docker image..."
docker build -t $ACR_LOGIN_SERVER/hotcalls-backend:staging -f Dockerfile .

print_status "Pushing backend image to ACR..."
docker push $ACR_LOGIN_SERVER/hotcalls-backend:staging

print_status "Creating ConfigMap..."
export ENVIRONMENT=staging
envsubst < k8s/configmap.yaml | sed 's/hotcalls-${ENVIRONMENT:-dev}/hotcalls-staging/g' | kubectl apply -f -

print_status "Deploying backend..."
cat k8s/deployment.yaml | \
  sed 's/${ENVIRONMENT:-dev}/staging/g' | \
  sed 's/${ACR_LOGIN_SERVER:-localhost:5000}/'$ACR_LOGIN_SERVER'/g' | \
  sed 's/${IMAGE_TAG:-latest}/staging/g' | \
  sed 's/${REPLICAS:-1}/2/g' | \
  kubectl apply -f -

print_status "Creating backend service..."
cat k8s/service.yaml | sed 's/hotcalls-${ENVIRONMENT:-dev}/hotcalls-staging/g' | kubectl apply -f -

# Step 8: Build and deploy frontend
print_section "Step 8: Building and Deploying Frontend"

print_status "Cloning frontend repository..."
if [ ! -d "../hotcalls-visual-prototype" ]; then
    git clone https://github.com/malmachengbr/hotcalls-visual-prototype.git ../hotcalls-visual-prototype
fi

cd ../hotcalls-visual-prototype
git checkout meta
git pull

print_status "Building frontend..."
if command -v bun &> /dev/null; then
    bun install && bun run build
else
    npm install && npm run build
fi

print_status "Building frontend Docker image..."
cp ../hotcalls/frontend-deploy/Dockerfile .
docker build -t $ACR_LOGIN_SERVER/hotcalls-frontend:staging .

print_status "Pushing frontend image to ACR..."
docker push $ACR_LOGIN_SERVER/hotcalls-frontend:staging

cd ../hotcalls

print_status "Deploying frontend..."
cat k8s/frontend-deployment.yaml | \
  sed 's/${ENVIRONMENT:-dev}/staging/g' | \
  sed 's/${ACR_LOGIN_SERVER:-localhost:5000}/'$ACR_LOGIN_SERVER'/g' | \
  sed 's/${IMAGE_TAG:-latest}/staging/g' | \
  sed 's/${FRONTEND_REPLICAS:-2}/2/g' | \
  kubectl apply -f -

print_status "Creating frontend service..."
cat k8s/frontend-service.yaml | sed 's/hotcalls-${ENVIRONMENT:-dev}/hotcalls-staging/g' | kubectl apply -f -

# Step 9: Install NGINX Ingress Controller
print_section "Step 9: Installing NGINX Ingress Controller"

print_status "Installing NGINX Ingress Controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/cloud/deploy.yaml

print_status "Waiting for NGINX Ingress Controller to be ready..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

# Get ingress IP
print_status "Getting ingress external IP..."
INGRESS_IP=""
while [ -z "$INGRESS_IP" ]; do
    INGRESS_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    if [ -z "$INGRESS_IP" ]; then
        print_status "Waiting for external IP..."
        sleep 10
    fi
done

# Step 10: Create TLS certificate and ingress
print_section "Step 10: Configuring Ingress"

print_status "Creating self-signed TLS certificate..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/tls.key -out /tmp/tls.crt \
  -subj "/CN=app1.hotcalls.ai" \
  -addext "subjectAltName = DNS:app1.hotcalls.ai"

kubectl create secret tls hotcalls-tls -n hotcalls-staging \
  --cert=/tmp/tls.crt \
  --key=/tmp/tls.key

print_status "Creating ingress..."
cat k8s/ingress.yaml | \
  sed 's/hotcalls-${ENVIRONMENT:-dev}/hotcalls-staging/g' | \
  sed 's/hotcalls-nginx-tls/hotcalls-tls/g' | \
  kubectl apply -f -

# Step 11: Run database migrations
print_section "Step 11: Running Database Migrations"

print_status "Waiting for backend pod to be ready..."
kubectl wait --namespace hotcalls-staging \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=backend \
  --timeout=120s || true

print_status "Running database migrations..."
BACKEND_POD=$(kubectl get pod -n hotcalls-staging -l app.kubernetes.io/component=backend -o jsonpath="{.items[0].metadata.name}")
kubectl exec -n hotcalls-staging $BACKEND_POD -- python manage.py migrate || true

# Final summary
print_section "Deployment Complete!"

echo -e "${GREEN}✅ Staging environment deployed successfully!${NC}"
echo
echo "External IP: ${INGRESS_IP}"
echo "Domain: app1.hotcalls.ai"
echo
echo "Configure DNS:"
echo "  Create A record: app1 -> ${INGRESS_IP}"
echo
echo "URLs:"
echo "  Frontend: https://app1.hotcalls.ai/"
echo "  API: https://app1.hotcalls.ai/api/"
echo "  API Docs: https://app1.hotcalls.ai/api/docs/"
echo
echo "Kubernetes namespace: hotcalls-staging"
echo
print_warning "Note: Using self-signed certificate. For production, set up cert-manager with Let's Encrypt." 