#!/bin/bash
set -e

echo "🚀 Deploying HotCalls to Kubernetes"
echo "===================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get ACR details
echo -e "${YELLOW}Getting ACR details...${NC}"
cd terraform
ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
cd ..

# Build and push image
echo -e "\n${YELLOW}Building Docker image...${NC}"
docker build -t hotcalls-backend:latest .

echo -e "\n${YELLOW}Tagging for ACR...${NC}"
docker tag hotcalls-backend:latest ${ACR_LOGIN_SERVER}/hotcalls-backend:latest

echo -e "\n${YELLOW}Logging into ACR...${NC}"
az acr login --name ${ACR_LOGIN_SERVER%%.*}

echo -e "\n${YELLOW}Pushing to ACR...${NC}"
docker push ${ACR_LOGIN_SERVER}/hotcalls-backend:latest

# Deploy to Kubernetes
echo -e "\n${YELLOW}Deploying to Kubernetes...${NC}"

# Create namespace if it doesn't exist
kubectl create namespace hotcalls-dev --dry-run=client -o yaml | kubectl apply -f -

# Set environment variables for substitution
export ENVIRONMENT=dev
export ACR_LOGIN_SERVER
export IMAGE_TAG=latest
export REPLICAS=1

# Apply manifests
echo -e "\n${YELLOW}Applying Kubernetes manifests...${NC}"
for manifest in namespace configmap secrets service deployment ingress; do
    echo "Applying ${manifest}.yaml..."
    envsubst < k8s/${manifest}.yaml | kubectl apply -f -
done

# Wait for deployment
echo -e "\n${YELLOW}Waiting for pods to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=hotcalls -n hotcalls-dev --timeout=300s

# Get ingress info
echo -e "\n${GREEN}✓ Deployment complete!${NC}"
echo -e "\n${YELLOW}Checking ingress status...${NC}"
kubectl get ingress -n hotcalls-dev

echo -e "\n${YELLOW}Pod status:${NC}"
kubectl get pods -n hotcalls-dev

echo -e "\n${GREEN}Done! Your app should be accessible soon.${NC}"
echo "Note: It may take a few minutes for the ingress to get an IP address." 