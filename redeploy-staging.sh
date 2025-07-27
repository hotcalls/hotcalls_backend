#!/bin/bash
set -e

echo "🚀 Starting staging deployment..."

# Default values
ENVIRONMENT="staging"
FORCE_ALL=false
RG_INDEX=""
DESTROY_MODE=false
DESTROY_RG=""
DESTROY_MODE=false
DESTROY_RG=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --force-all)
      FORCE_ALL=true
      shift
      ;;
    --rg-index)
      RG_INDEX="-index-$2"
      shift 2
      ;;
    --destroy)
      DESTROY_MODE=true
      DESTROY_RG="$2"
      shift 2
      ;;
    --destroy)
      DESTROY_MODE=true
      DESTROY_RG="$2"
      shift 2
      ;;
    *)
      ENVIRONMENT="$1"
      shift
      ;;
  esac
done

# Handle destroy mode
if [ "$DESTROY_MODE" = true ]; then
  if [ -z "$DESTROY_RG" ]; then
    echo "❌ Error: --destroy requires a resource group name"
    echo "Usage: $0 --destroy <resource-group-name>"
    echo "Example: $0 --destroy hotcalls-staging-index-1-ne-rg"
    exit 1
  fi
  
  echo "🚨 DESTRUCTION MODE ACTIVATED 🚨"
  echo ""
  echo "Resource Group to destroy: $DESTROY_RG"
  echo ""
  echo "⚠️  WARNING: This will PERMANENTLY DELETE all resources in the resource group:"
  echo "   - AKS Cluster and all applications"
  echo "   - PostgreSQL database and all data"
  echo "   - Storage accounts and all files"
  echo "   - Container registries and all images"
  echo "   - All networking components"
  echo "   - All monitoring and logging data"
  echo ""
  echo "💀 THIS ACTION CANNOT BE UNDONE! 💀"
  echo ""
  
  # Check if resource group exists
  if ! az group show --name "$DESTROY_RG" &> /dev/null; then
    echo "❌ Resource group '$DESTROY_RG' does not exist or you don't have access to it."
    exit 1
  fi
  
  # Show resources in the group
  echo "📋 Resources found in '$DESTROY_RG':"
  az resource list --resource-group "$DESTROY_RG" --query "[].{Name:name, Type:type}" --output table
  echo ""
  
  # First confirmation
  read -p "❓ Are you absolutely sure you want to destroy resource group '$DESTROY_RG'? (type 'yes' to confirm): " -r
  if [[ ! $REPLY == "yes" ]]; then
    echo "✅ Destruction cancelled."
    exit 0
  fi
  
  # Second confirmation
  read -p "❓ This is your final warning. Type the resource group name to confirm: " -r
  if [[ ! $REPLY == "$DESTROY_RG" ]]; then
    echo "✅ Destruction cancelled (resource group name mismatch)."
    exit 0
  fi
  
  echo ""
  echo "💥 Starting destruction of resource group '$DESTROY_RG'..."
  echo "⏳ This may take several minutes..."
  
  if az group delete --name "$DESTROY_RG" --yes --no-wait; then
    echo "✅ Destruction initiated successfully!"
    echo "📊 You can monitor progress with:"
    echo "   az group show --name '$DESTROY_RG' --query 'properties.provisioningState'"
    echo ""
    echo "🕐 The resource group will be completely removed in 5-15 minutes."
  else
    echo "❌ Failed to initiate destruction. Check your permissions and try again."
    exit 1
  fi
  
  exit 0
fi

# Handle destroy mode
if [ "$DESTROY_MODE" = true ]; then
  if [ -z "$DESTROY_RG" ]; then
    echo "❌ Error: --destroy requires a resource group name"
    echo "Usage: $0 --destroy <resource-group-name>"
    echo "Example: $0 --destroy hotcalls-staging-index-1-ne-rg"
    exit 1
  fi
  
  echo "🚨 DESTRUCTION MODE ACTIVATED 🚨"
  echo ""
  echo "Resource Group to destroy: $DESTROY_RG"
  echo ""
  echo "⚠️  WARNING: This will PERMANENTLY DELETE all resources in the resource group:"
  echo "   - AKS Cluster and all applications"
  echo "   - PostgreSQL database and all data"
  echo "   - Storage accounts and all files"
  echo "   - Container registries and all images"
  echo "   - All networking components"
  echo "   - All monitoring and logging data"
  echo ""
  echo "💀 THIS ACTION CANNOT BE UNDONE! 💀"
  echo ""
  
  # Check if resource group exists
  if ! az group show --name "$DESTROY_RG" &> /dev/null; then
    echo "❌ Resource group '$DESTROY_RG' does not exist or you don't have access to it."
    exit 1
  fi
  
  # Show resources in the group
  echo "📋 Resources found in '$DESTROY_RG':"
  az resource list --resource-group "$DESTROY_RG" --query "[].{Name:name, Type:type}" --output table
  echo ""
  
  # First confirmation
  read -p "❓ Are you absolutely sure you want to destroy resource group '$DESTROY_RG'? (type 'yes' to confirm): " -r
  if [[ ! $REPLY == "yes" ]]; then
    echo "✅ Destruction cancelled."
    exit 0
  fi
  
  # Second confirmation
  read -p "❓ This is your final warning. Type the resource group name to confirm: " -r
  if [[ ! $REPLY == "$DESTROY_RG" ]]; then
    echo "✅ Destruction cancelled (resource group name mismatch)."
    exit 0
  fi
  
  echo ""
  echo "💥 Starting destruction of resource group '$DESTROY_RG'..."
  echo "⏳ This may take several minutes..."
  
  if az group delete --name "$DESTROY_RG" --yes --no-wait; then
    echo "✅ Destruction initiated successfully!"
    echo "📊 You can monitor progress with:"
    echo "   az group show --name '$DESTROY_RG' --query 'properties.provisioningState'"
    echo ""
    echo "🕐 The resource group will be completely removed in 5-15 minutes."
  else
    echo "❌ Failed to initiate destruction. Check your permissions and try again."
    exit 1
  fi
  
  exit 0
fi

# Variables  
if [ ! -z "$RG_INDEX" ]; then
  ENVIRONMENT="${ENVIRONMENT}${RG_INDEX}"  # Update environment to include index
  RESOURCE_GROUP="hotcalls-${ENVIRONMENT}-ne-rg"
  AKS_CLUSTER="hotcalls-${ENVIRONMENT}-ne-aks"
else
  RESOURCE_GROUP="hotcalls-${ENVIRONMENT}-ne-rg"
  AKS_CLUSTER="hotcalls-${ENVIRONMENT}-ne-aks"
fi
BRANCH=$(echo ${ENVIRONMENT} | sed 's/-index-[0-9]*$//')  # Use base environment name as branch name

echo "📋 Deployment Configuration:"
echo "   Environment: ${ENVIRONMENT}"
echo "   Resource Group: ${RESOURCE_GROUP}"
echo "   AKS Cluster: ${AKS_CLUSTER}"
echo "   Force Terraform: ${FORCE_ALL}"
echo "   Branch: ${BRANCH}"

# Ensure we're on the correct branch and have latest code
echo "🔄 Switching to ${BRANCH} branch and pulling latest changes..."
git checkout $BRANCH
git pull origin $BRANCH

# Terraform management
cd terraform

# Set workspace name based on environment (already includes index if specified)
WORKSPACE_NAME="${ENVIRONMENT}"

echo "🔄 Managing Terraform workspace: $WORKSPACE_NAME"

# Initialize and select/create workspace
terraform init

# Create workspace if it doesn't exist, otherwise select it
echo "📁 Selecting workspace: $WORKSPACE_NAME"
if ! terraform workspace select "$WORKSPACE_NAME" 2>/dev/null; then
  echo "📁 Workspace doesn't exist, creating new workspace: $WORKSPACE_NAME"
  terraform workspace new "$WORKSPACE_NAME"
fi

# Create dynamic tfvars if index is specified
TFVARS_FILE="staging.tfvars"
if [ ! -z "$RG_INDEX" ]; then
  TFVARS_FILE="staging-index.tfvars"
  echo "📝 Creating dynamic tfvars with index suffix..."
  
  # Create a modified tfvars file with indexed environment name
  sed "s/environment[[:space:]]*=[[:space:]]*\"staging\"/environment = \"${ENVIRONMENT}\"/g" staging.tfvars > $TFVARS_FILE
  sed -i '' "s/hotcalls-staging.svc.cluster.local/hotcalls-${ENVIRONMENT}.svc.cluster.local/g" $TFVARS_FILE
  sed -i '' "s/Environment[[:space:]]*=[[:space:]]*\"Staging\"/Environment = \"$(echo ${ENVIRONMENT} | sed 's/.*/\L&/' | sed 's/\b./\u&/g')\"/g" $TFVARS_FILE
fi

if [ "$FORCE_ALL" = true ]; then
  echo "💥 Force mode: Destroying and recreating infrastructure..."
  
  # Check if infrastructure exists and destroy it
  if terraform state list &> /dev/null && [ $(terraform state list | wc -l) -gt 0 ]; then
    echo "🗑️ Destroying existing infrastructure..."
    terraform destroy -auto-approve -var-file="$TFVARS_FILE"
    terraform destroy -auto-approve -var-file="$TFVARS_FILE"
  fi
  
  echo "🏗️ Creating new infrastructure..."
  terraform apply -auto-approve -var-file="$TFVARS_FILE"
  terraform apply -auto-approve -var-file="$TFVARS_FILE"
    
elif ! terraform state list &> /dev/null || [ $(terraform state list | wc -l) -eq 0 ] || ! terraform output acr_login_server &> /dev/null; then
elif ! terraform state list &> /dev/null || [ $(terraform state list | wc -l) -eq 0 ] || ! terraform output acr_login_server &> /dev/null; then
  echo "🏗️ No infrastructure found, creating new infrastructure..."
  terraform apply -auto-approve -var-file="$TFVARS_FILE"
  terraform apply -auto-approve -var-file="$TFVARS_FILE"
else
  echo "✅ Infrastructure exists, skipping Terraform deployment..."
fi

# Clean up temporary tfvars file
if [ ! -z "$RG_INDEX" ] && [ -f "$TFVARS_FILE" ]; then
  rm "$TFVARS_FILE"
fi

# Clean up temporary tfvars file
if [ ! -z "$RG_INDEX" ] && [ -f "$TFVARS_FILE" ]; then
  rm "$TFVARS_FILE"
fi

echo "📦 Getting Terraform outputs..."
ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
ACR_NAME=$(echo $ACR_LOGIN_SERVER | cut -d'.' -f1)
POSTGRES_FQDN=$(terraform output -raw postgres_fqdn)
POSTGRES_SERVER_NAME=$(echo $POSTGRES_FQDN | cut -d'.' -f1)
POSTGRES_SERVER_NAME=$(echo $POSTGRES_FQDN | cut -d'.' -f1)
STORAGE_ACCOUNT=$(terraform output -raw storage_account_name)
STORAGE_KEY=$(terraform output -raw storage_account_primary_access_key)

echo "🔓 Configuring PostgreSQL firewall to allow Azure services..."
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER_NAME \
  --rule-name "AllowAzureServices" \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 || echo "Firewall rule already exists"

STORAGE_KEY=$(terraform output -raw storage_account_primary_access_key)

echo "🔓 Configuring PostgreSQL firewall to allow Azure services..."
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER_NAME \
  --rule-name "AllowAzureServices" \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 || echo "Firewall rule already exists"

cd ..

# Configure kubectl
echo "🔧 Configuring kubectl..."
az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER --admin --overwrite-existing

# Create namespace
echo "📁 Creating namespace..."
kubectl create namespace hotcalls-${ENVIRONMENT} --dry-run=client -o yaml | kubectl apply -f -

# Create secrets
echo "🔐 Creating secrets with proper database connection..."
echo "Database Host: $POSTGRES_FQDN"
echo "Storage Account: $STORAGE_ACCOUNT"

kubectl create secret generic hotcalls-secrets \
  --namespace=hotcalls-${ENVIRONMENT} \
  --from-literal=SECRET_KEY="django-insecure-dev-key" \
  --from-literal=ALLOWED_HOSTS="*" \
  --from-literal=DB_NAME="hotcalls" \
  --from-literal=DB_USER="hotcallsadmin" \
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
  --from-literal=AZURE_KEY_VAULT_URL="" \
  --from-literal=AZURE_CLIENT_ID="" \
  --from-literal=AZURE_MONITOR_CONNECTION_STRING="" \
  --from-literal=CORS_ALLOWED_ORIGINS="*" \
  --from-literal=BASE_URL="http://localhost:8000" \
  --dry-run=client -o yaml | kubectl apply -f -

# Deploy Redis
echo "🔴 Deploying Redis..."
kubectl apply -n hotcalls-${ENVIRONMENT} -f - << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
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
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
EOF

# Login to ACR
echo "🔑 Logging into ACR..."
az acr login --name $ACR_NAME

# Build and push backend
echo "🏗️ Building backend..."
docker build -t ${ACR_LOGIN_SERVER}/hotcalls-backend:${ENVIRONMENT} .
docker push ${ACR_LOGIN_SERVER}/hotcalls-backend:${ENVIRONMENT}

# Create ConfigMap
echo "⚙️ Creating ConfigMap..."
kubectl apply -n hotcalls-${ENVIRONMENT} -f - << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: hotcalls-config
data:
  ENVIRONMENT: "${ENVIRONMENT}"
  DEBUG: "False"
  TIME_ZONE: "Europe/Berlin"
  DB_ENGINE: "django.db.backends.postgresql"
  DB_PORT: "5432"
  DB_SSLMODE: "require"
  REDIS_PORT: "6379"
  REDIS_DB: "0"
  AZURE_STATIC_CONTAINER: "static"
  AZURE_MEDIA_CONTAINER: "media"
  SECURE_SSL_REDIRECT: "False"
  SESSION_COOKIE_SECURE: "False"
  CSRF_COOKIE_SECURE: "False"
  LOG_LEVEL: "INFO"
EOF

# Deploy backend
echo "🚀 Deploying backend..."
kubectl apply -n hotcalls-${ENVIRONMENT} -f - << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hotcalls-backend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hotcalls-backend
  template:
    metadata:
      labels:
        app: hotcalls-backend
    spec:
      containers:
      - name: backend
        image: ${ACR_LOGIN_SERVER}/hotcalls-backend:${ENVIRONMENT}
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: hotcalls-config
        - secretRef:
            name: hotcalls-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: hotcalls-backend-service
spec:
  selector:
    app: hotcalls-backend
  ports:
  - port: 80
    targetPort: 8000
EOF

# Build and push frontend (from visual prototype repo)
echo "🏗️ Building frontend..."
if [ -d "../hotcalls-visual-prototype" ]; then
  cd ../hotcalls-visual-prototype
  
  # Switch to the correct branch and pull latest changes
  echo "🔄 Switching frontend repo to ${BRANCH} branch..."
  
  # Check if branch exists, otherwise use default branch
  if git show-ref --verify --quiet refs/heads/$BRANCH; then
    git checkout $BRANCH
    git pull origin $BRANCH
  elif git show-ref --verify --quiet refs/remotes/origin/$BRANCH; then
    git checkout -b $BRANCH origin/$BRANCH
  else
    echo "⚠️ Branch $BRANCH not found, using default branch..."
    git checkout $(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@') 2>/dev/null || git checkout main 2>/dev/null || git checkout master
    git pull
  fi
  
  # Check if branch exists, otherwise use default branch
  if git show-ref --verify --quiet refs/heads/$BRANCH; then
    git checkout $BRANCH
    git pull origin $BRANCH
  elif git show-ref --verify --quiet refs/remotes/origin/$BRANCH; then
    git checkout -b $BRANCH origin/$BRANCH
  else
    echo "⚠️ Branch $BRANCH not found, using default branch..."
    git checkout $(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@') 2>/dev/null || git checkout main 2>/dev/null || git checkout master
    git pull
  fi
  
  docker build -f ../hotcalls/frontend-deploy/Dockerfile -t ${ACR_LOGIN_SERVER}/hotcalls-frontend:${ENVIRONMENT} .
  docker push ${ACR_LOGIN_SERVER}/hotcalls-frontend:${ENVIRONMENT}
  cd ../hotcalls
else
  echo "⚠️ Frontend repo not found, skipping frontend deployment"
fi

# Deploy frontend
echo "🚀 Deploying frontend..."
kubectl apply -n hotcalls-${ENVIRONMENT} -f - << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hotcalls-frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hotcalls-frontend
  template:
    metadata:
      labels:
        app: hotcalls-frontend
    spec:
      containers:
      - name: frontend
        image: ${ACR_LOGIN_SERVER}/hotcalls-frontend:${ENVIRONMENT}
        ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: hotcalls-frontend-service
spec:
  selector:
    app: hotcalls-frontend
  ports:
  - port: 80
    targetPort: 8080
EOF

# Create ACR pull secret
echo "🔐 Creating ACR pull secret..."
ACR_USER=$(az acr credential show -n $ACR_NAME --query username -o tsv)
ACR_PASS=$(az acr credential show -n $ACR_NAME --query 'passwords[0].value' -o tsv)
kubectl create secret docker-registry acr-secret -n hotcalls-${ENVIRONMENT} \
  --docker-server=${ACR_LOGIN_SERVER} \
  --docker-username=$ACR_USER \
  --docker-password=$ACR_PASS \
  --dry-run=client -o yaml | kubectl apply -f -

# Patch deployments to use pull secret
echo "🔧 Patching deployments..."
kubectl patch deployment hotcalls-backend -n hotcalls-${ENVIRONMENT} \
  -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"acr-secret"}]}}}}'
kubectl patch deployment hotcalls-frontend -n hotcalls-${ENVIRONMENT} \
  -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"acr-secret"}]}}}}'

# Install NGINX Ingress Controller (if not exists)
echo "🌐 Installing NGINX Ingress Controller..."
kubectl get namespace ingress-nginx &> /dev/null || \
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/cloud/deploy.yaml

# Create Ingress with retry logic
echo "🌐 Creating Ingress..."
for i in {1..5}; do
  echo "Ingress creation attempt $i/5..."
  if kubectl apply -n hotcalls-${ENVIRONMENT} -f - << EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hotcalls-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
spec:
  ingressClassName: nginx
  rules:
  - http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: hotcalls-backend-service
            port:
              number: 80
      - path: /
        pathType: Prefix
        backend:
          service:
            name: hotcalls-frontend-service
            port:
              number: 80
EOF
  then
    echo "✅ Ingress created successfully!"
    break
  else
    echo "⚠️ Ingress creation attempt $i failed, retrying in 10 seconds..."
    sleep 10
  fi
  if [ $i -eq 5 ]; then
    echo "❌ All ingress creation attempts failed!"
    exit 1
  fi
done

# Wait for NGINX Ingress Controller to be ready
echo "⏳ Waiting for NGINX Ingress Controller to be ready..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=300s

# Wait for pods to be ready with better timeout and error handling
echo "⏳ Waiting for all pods to be ready (max 2 minutes)..."
if ! kubectl wait --namespace hotcalls-${ENVIRONMENT} --for=condition=ready pod --all --timeout=120s; then
  echo "⚠️ Some pods not ready after 2 minutes, checking status..."
  kubectl get pods -n hotcalls-${ENVIRONMENT}
  echo "🚀 Continuing with deployment (pods may still be starting)..."
fi

# Run database migrations with faster retry
echo "🗃️ Running database migrations..."
echo "Waiting for backend to be ready..."
sleep 5

# Retry migrations up to 3 times with shorter waits
for i in {1..3}; do
  echo "Migration attempt $i/3..."
  if kubectl exec -n hotcalls-${ENVIRONMENT} deployment/hotcalls-backend -- python manage.py migrate; then
    echo "✅ Migrations completed successfully!"
    break
  else
    echo "⚠️ Migration attempt $i failed, retrying in 5 seconds..."
    sleep 5
  fi
  if [ $i -eq 3 ]; then
    echo "⚠️ All migration attempts failed, but deployment continues..."
    echo "💡 You can run migrations manually later with:"
    echo "   kubectl exec -n hotcalls-${ENVIRONMENT} deployment/hotcalls-backend -- python manage.py migrate"
  fi
done

# Wait for external IP (max 2 minutes)
echo "⏳ Waiting for external IP (max 2 minutes)..."
for i in {1..24}; do
  EXTERNAL_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
  if [ ! -z "$EXTERNAL_IP" ]; then
    echo ""
    echo "🎉 External IP assigned: $EXTERNAL_IP"
    break
  fi
  echo -n "."
  sleep 5
  if [ $i -eq 24 ]; then
    echo ""
    echo "⚠️ External IP not assigned yet. Check manually with:"
    echo "   kubectl get svc -n ingress-nginx ingress-nginx-controller"
  fi
done

# Validate deployment
echo "🔍 Validating deployment..."

# Quick health checks (max 30 seconds total)
if [ ! -z "$EXTERNAL_IP" ]; then
  echo "Quick frontend test..."
  for i in {1..3}; do
    if curl -m 5 -s -f "http://$EXTERNAL_IP/" > /dev/null 2>&1; then
      echo "✅ Frontend health check passed!"
      break
    else
      echo "⏳ Frontend test $i/3..."
      sleep 2
    fi
    if [ $i -eq 3 ]; then
      echo "⚠️ Frontend not responding yet (may need more time)"
    fi
  done
  
  echo "Quick API test..."
  for i in {1..3}; do
    if curl -m 5 -s -f "http://$EXTERNAL_IP/health/" > /dev/null 2>&1; then
      echo "✅ API health check passed!"
      break
    else
      echo "⏳ API test $i/3..."
      sleep 2
    fi
    if [ $i -eq 3 ]; then
      echo "⚠️ API not responding yet (may need more time)"
    fi
  done
fi

# Final status
echo "✅ Deployment complete!"
echo ""
echo "📊 Pod Status:"
kubectl get pods -n hotcalls-${ENVIRONMENT}
echo ""
if [ ! -z "$EXTERNAL_IP" ]; then
  echo "🌐 External IP: $EXTERNAL_IP"
  echo "- Frontend: http://$EXTERNAL_IP/"
  echo "- API: http://$EXTERNAL_IP/api/"
  echo "- API Docs: http://$EXTERNAL_IP/api/docs/"
else
  echo "⚠️ External IP not yet assigned. Check with:"
  echo "kubectl get svc -n ingress-nginx ingress-nginx-controller"
fi

echo ""
echo "💡 Usage examples:"
echo "   ./redeploy-staging.sh                    # Deploy to default staging"
echo "   ./redeploy-staging.sh --force-all        # Recreate infrastructure + deploy"
echo "   ./redeploy-staging.sh --rg-index 2       # Deploy to hotcalls-staging-ne-rg-index-2"
echo "   ./redeploy-staging.sh staging --rg-index 1 --force-all  # Full recreate with index"
echo ""
echo "🗑️  Destroy examples:"
echo "   ./redeploy-staging.sh --destroy hotcalls-staging-index-1-ne-rg    # Destroy specific RG"
echo "   ./redeploy-staging.sh --destroy hotcalls-staging-ne-rg           # Destroy default staging" 
echo "   ./redeploy-staging.sh staging --rg-index 1 --force-all  # Full recreate with index"
echo ""
echo "🗑️  Destroy examples:"
echo "   ./redeploy-staging.sh --destroy hotcalls-staging-index-1-ne-rg    # Destroy specific RG"
echo "   ./redeploy-staging.sh --destroy hotcalls-staging-ne-rg           # Destroy default staging" 