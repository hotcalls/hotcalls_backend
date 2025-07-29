#!/bin/bash

# Frontend Deployment Script for Hotcalls
# This script will build and deploy the frontend to Azure Kubernetes Service

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check if environment variables are set
if [ -z "$ENVIRONMENT" ]; then
    print_error "ENVIRONMENT variable not set. Please set it to 'dev', 'staging', or 'prod'"
    exit 1
fi

if [ -z "$ACR_LOGIN_SERVER" ]; then
    print_error "ACR_LOGIN_SERVER variable not set. Please run: export ACR_LOGIN_SERVER=<your-acr-name>.azurecr.io"
    exit 1
fi

# Set default values
IMAGE_TAG=${IMAGE_TAG:-latest}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

print_status "Starting frontend deployment process..."
print_status "Environment: $ENVIRONMENT"
print_status "ACR: $ACR_LOGIN_SERVER"
print_status "Image tag: $IMAGE_TAG"
print_status "Using local frontend at: $FRONTEND_DIR"

# Step 1: Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    print_error "Frontend directory not found at $FRONTEND_DIR"
    exit 1
fi

# Step 2: Navigate to frontend directory
cd "$FRONTEND_DIR"
print_status "Working in frontend directory: $(pwd)"

# Step 3: Install dependencies and build
print_status "Installing dependencies..."
if command -v bun &> /dev/null; then
    bun install
else
    print_warning "Bun not found, using npm instead..."
    npm install
fi

print_status "Building frontend..."
if command -v bun &> /dev/null; then
    bun run build
else
    npm run build
fi

# Check if build output exists
if [ -d "dist" ]; then
    BUILD_DIR="dist"
elif [ -d "build" ]; then
    BUILD_DIR="build"
else
    print_error "Build output directory not found. Expected 'dist' or 'build' directory."
    exit 1
fi

print_status "Build output found in $BUILD_DIR directory"

# Step 4: Copy Dockerfile to frontend directory
print_status "Copying Dockerfile..."
cp "$SCRIPT_DIR/Dockerfile" .

# Update Dockerfile to use correct build directory
if [ "$BUILD_DIR" = "build" ]; then
    sed -i.bak 's/COPY dist\//COPY build\//' Dockerfile && rm Dockerfile.bak
fi

# Step 5: Build Docker image
print_status "Building Docker image..."
docker build -t $ACR_LOGIN_SERVER/hotcalls-frontend:$IMAGE_TAG .

# Step 6: Login to ACR
print_status "Logging in to Azure Container Registry..."
az acr login --name ${ACR_LOGIN_SERVER%%.*}

# Step 7: Push image to ACR
print_status "Pushing image to ACR..."
docker push $ACR_LOGIN_SERVER/hotcalls-frontend:$IMAGE_TAG

# Step 8: Deploy to Kubernetes
cd "$SCRIPT_DIR/.."
print_status "Deploying frontend to Kubernetes..."

# Set project prefix based on environment
PROJECT_PREFIX="hotcalls"

# Apply frontend deployment
print_status "Applying frontend deployment..."
export ENVIRONMENT=$ENVIRONMENT
export ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER
export IMAGE_TAG=$IMAGE_TAG
export PROJECT_PREFIX=$PROJECT_PREFIX
export FRONTEND_REPLICAS=${FRONTEND_REPLICAS:-2}

envsubst < k8s/frontend-deployment.yaml | kubectl apply -f -

# Apply frontend service
print_status "Applying frontend service..."
envsubst < k8s/frontend-service.yaml | kubectl apply -f -

# Apply updated ingress
print_status "Applying updated ingress..."
envsubst < k8s/ingress.yaml | kubectl apply -f -

# Wait for deployment to be ready
print_status "Waiting for frontend deployment to be ready..."
kubectl rollout status deployment/${PROJECT_PREFIX}-frontend -n ${PROJECT_PREFIX}-$ENVIRONMENT

# Check pod status
print_status "Checking pod status..."
kubectl get pods -n ${PROJECT_PREFIX}-$ENVIRONMENT -l app.kubernetes.io/component=frontend

print_status "Frontend deployment completed successfully!"
print_status "Access your application at your configured domain"

# Display ingress details
print_status "Ingress details:"
kubectl get ingress -n ${PROJECT_PREFIX}-$ENVIRONMENT 