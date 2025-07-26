#!/bin/bash
set -e

echo "🚀 HotCalls Deployment Script - Production Stack Update"
echo "======================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo -e "${RED}Error: Not in project root. Please run from hotcalls root directory.${NC}"
    exit 1
fi

# Get ACR details from Terraform
echo -e "\n${YELLOW}Step 1: Getting ACR details from Terraform...${NC}"
cd terraform
ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server 2>/dev/null || echo "")
cd ..

if [ -z "$ACR_LOGIN_SERVER" ]; then
    echo -e "${RED}Error: Could not get ACR login server. Run 'terraform output acr_login_server' manually.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ ACR Login Server: $ACR_LOGIN_SERVER${NC}"

# Step 1: Build and push Docker image
echo -e "\n${YELLOW}Step 2: Building Docker image (production-only)...${NC}"
docker build -t hotcalls-backend:latest .

echo -e "\n${YELLOW}Step 3: Tagging image for ACR...${NC}"
docker tag hotcalls-backend:latest ${ACR_LOGIN_SERVER}/hotcalls-backend:latest

echo -e "\n${YELLOW}Step 4: Logging into ACR...${NC}"
az acr login --name ${ACR_LOGIN_SERVER%%.*}

echo -e "\n${YELLOW}Step 5: Pushing image to ACR...${NC}"
docker push ${ACR_LOGIN_SERVER}/hotcalls-backend:latest

# Step 2: Apply Terraform changes
echo -e "\n${YELLOW}Step 6: Applying Terraform changes (enabling APIM)...${NC}"
cd terraform

echo "Planning changes..."
terraform plan -var-file=dev.tfvars -out=tfplan

echo -e "\n${YELLOW}Applying changes (this will take ~20 minutes for APIM)...${NC}"
terraform apply tfplan

# Get the APIM URL
APIM_URL=$(terraform output -raw apim_gateway_url)
echo -e "\n${GREEN}✓ APIM Gateway URL: $APIM_URL${NC}"

cd ..

# Step 3: Update Kubernetes deployments
echo -e "\n${YELLOW}Step 7: Updating Kubernetes deployments...${NC}"

# Get AKS credentials if not already configured
CLUSTER_NAME=$(cd terraform && terraform output -raw aks_cluster_name && cd ..)
RESOURCE_GROUP=$(cd terraform && terraform output -raw resource_group_name && cd ..)

echo "Configuring kubectl..."
az aks get-credentials --resource-group $RESOURCE_GROUP --name $CLUSTER_NAME --overwrite-existing

# Update deployments with new image
echo -e "\n${YELLOW}Rolling out new image to all deployments...${NC}"
kubectl set image deployment/hotcalls-backend hotcalls-backend=${ACR_LOGIN_SERVER}/hotcalls-backend:latest -n hotcalls-dev
kubectl set image deployment/hotcalls-celery-worker celery-worker=${ACR_LOGIN_SERVER}/hotcalls-backend:latest -n hotcalls-dev
kubectl set image deployment/hotcalls-celery-beat celery-beat=${ACR_LOGIN_SERVER}/hotcalls-backend:latest -n hotcalls-dev

# Wait for rollout
echo -e "\n${YELLOW}Waiting for rollout to complete...${NC}"
kubectl rollout status deployment/hotcalls-backend -n hotcalls-dev
kubectl rollout status deployment/hotcalls-celery-worker -n hotcalls-dev
kubectl rollout status deployment/hotcalls-celery-beat -n hotcalls-dev

# Step 4: Verify deployment
echo -e "\n${YELLOW}Step 8: Verifying deployment...${NC}"

# Check pod status
echo "Current pod status:"
kubectl get pods -n hotcalls-dev

# Test APIM endpoint
echo -e "\n${YELLOW}Testing APIM health endpoint...${NC}"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://${APIM_URL}/api/health/ || echo "Failed")

if [ "$HEALTH_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ API Health check passed!${NC}"
else
    echo -e "${RED}✗ API Health check failed (HTTP $HEALTH_STATUS)${NC}"
    echo "This might be normal if APIM is still initializing. Wait a few minutes and try:"
    echo "curl https://${APIM_URL}/api/health/"
fi

echo -e "\n${GREEN}🎉 Deployment Complete!${NC}"
echo "======================================"
echo "APIM Gateway URL: https://${APIM_URL}"
echo "API Endpoints: https://${APIM_URL}/api/"
echo "Swagger Docs: https://${APIM_URL}/api/docs/"
echo "======================================" 