#!/bin/bash
set -e

echo "🚀 Starting staging deployment..."

# Variables
ENVIRONMENT=${1:-staging}
RESOURCE_GROUP="hotcalls-${ENVIRONMENT}-ne-rg"
AKS_CLUSTER="hotcalls-${ENVIRONMENT}-ne-aks"

# Terraform outputs
cd terraform
echo "📦 Getting Terraform outputs..."
ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
ACR_NAME=$(echo $ACR_LOGIN_SERVER | cut -d'.' -f1)
POSTGRES_FQDN=$(terraform output -raw postgres_fqdn)
STORAGE_ACCOUNT=$(terraform output -raw storage_account_name)
STORAGE_KEY=$(terraform output -raw storage_primary_access_key)
cd ..

# Configure kubectl
echo "🔧 Configuring kubectl..."
az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER --admin --overwrite-existing

# Create namespace
echo "📁 Creating namespace..."
kubectl create namespace hotcalls-${ENVIRONMENT} --dry-run=client -o yaml | kubectl apply -f -

# Create secrets
echo "🔐 Creating secrets..."
cat > secrets.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: hotcalls-secrets
  namespace: hotcalls-${ENVIRONMENT}
type: Opaque
stringData:
  SECRET_KEY: "django-insecure-dev-key"
  ALLOWED_HOSTS: "*"
  DB_NAME: "hotcalls"
  DB_USER: "hotcallsadmin"
  DB_PASSWORD: "ChangeMe123!"
  DB_HOST: "${POSTGRES_FQDN}"
  REDIS_HOST: "redis-service"
  REDIS_PORT: "6379"
  REDIS_DB: "0"
  REDIS_PASSWORD: ""
  CELERY_BROKER_URL: "redis://redis-service:6379/0"
  CELERY_RESULT_BACKEND: "redis://redis-service:6379/0"
  AZURE_ACCOUNT_NAME: "${STORAGE_ACCOUNT}"
  AZURE_STORAGE_KEY: "${STORAGE_KEY}"
  AZURE_CUSTOM_DOMAIN: ""
  AZURE_KEY_VAULT_URL: ""
  AZURE_CLIENT_ID: ""
  AZURE_MONITOR_CONNECTION_STRING: ""
  CORS_ALLOWED_ORIGINS: "*"
  BASE_URL: "http://localhost:8000"
EOF
kubectl apply -f secrets.yaml
rm secrets.yaml

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

# Create Ingress
echo "🌐 Creating Ingress..."
kubectl apply -n hotcalls-${ENVIRONMENT} -f - << EOF
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

# Wait for external IP
echo "⏳ Waiting for external IP..."
for i in {1..60}; do
  EXTERNAL_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
  if [ ! -z "$EXTERNAL_IP" ]; then
    break
  fi
  echo -n "."
  sleep 5
done
echo ""

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