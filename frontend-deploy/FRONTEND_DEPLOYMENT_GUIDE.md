# Frontend Deployment Guide for Hotcalls

This guide will help you deploy the Hotcalls frontend alongside the backend on the same domain (app1.hotcalls.ai).

## Prerequisites

1. Azure CLI installed and logged in
2. kubectl configured for your AKS cluster  
3. Docker installed
4. Node.js/npm or Bun installed
5. Access to the ACR (Azure Container Registry)

## Architecture Overview

- Frontend: React app served by NGINX at `/`
- Backend: Django API served at `/api/*`
- Both services behind the same ingress on `app1.hotcalls.ai`

## Step-by-Step Deployment

### 1. Set Environment Variables

First, get your ACR login server from Terraform outputs [[memory:4414305]]:

```bash
cd terraform
terraform output -raw acr_login_server
```

Then set the required environment variables:

```bash
export ENVIRONMENT=dev  # or staging/prod
export ACR_LOGIN_SERVER=<your-acr-name>.azurecr.io  # From terraform output
export IMAGE_TAG=latest  # or specific version
```

### 2. Update Backend Configuration

Update the backend to accept requests from the new domain:

```bash
# Update ALLOWED_HOSTS to include app1.hotcalls.ai
export ALLOWED_HOSTS="localhost,127.0.0.1,app1.hotcalls.ai"

# Update CORS to allow frontend origin
export CORS_ALLOWED_ORIGINS="https://app1.hotcalls.ai"

# Apply the updated secrets
envsubst < k8s/secrets.yaml | kubectl apply -f -
```

### 3. Deploy the Frontend

Run the automated deployment script:

```bash
cd /Users/martinb/Documents/hotcalls
./frontend-deploy/deploy-frontend.sh
```

This script will:
1. Clone the frontend repo (if needed)
2. Checkout the `meta` branch
3. Install dependencies with bun/npm
4. Build the static files
5. Build and push the Docker image to ACR
6. Deploy to Kubernetes

### 4. Manual Deployment (Alternative)

If you prefer to run the steps manually:

```bash
# Clone and build frontend
git clone https://github.com/malmachengbr/hotcalls-visual-prototype.git ../hotcalls-visual-prototype
cd ../hotcalls-visual-prototype
git checkout meta
bun install  # or npm install
bun run build  # or npm run build

# Build Docker image
cp ../hotcalls/frontend-deploy/Dockerfile .
docker build -t $ACR_LOGIN_SERVER/hotcalls-frontend:$IMAGE_TAG .

# Push to ACR
az acr login --name ${ACR_LOGIN_SERVER%%.*}
docker push $ACR_LOGIN_SERVER/hotcalls-frontend:$IMAGE_TAG

# Deploy to Kubernetes
cd ../hotcalls
envsubst < k8s/frontend-deployment.yaml | kubectl apply -f -
envsubst < k8s/frontend-service.yaml | kubectl apply -f -
envsubst < k8s/ingress.yaml | kubectl apply -f -
```

### 5. Verify Deployment

Check that all pods are running:

```bash
kubectl get pods -n hotcalls-$ENVIRONMENT
```

Check the ingress configuration:

```bash
kubectl get ingress -n hotcalls-$ENVIRONMENT
kubectl describe ingress hotcalls-ingress -n hotcalls-$ENVIRONMENT
```

## DNS Configuration

Configure DNS for `app1.hotcalls.ai` in IONOS:

1. Get the ingress external IP/hostname:
   ```bash
   kubectl get ingress -n hotcalls-$ENVIRONMENT
   ```

2. In IONOS DNS settings:
   - If you get an IP: Create an A record for `app1` pointing to that IP
   - If you get a hostname: Create a CNAME record for `app1` pointing to that hostname

## Troubleshooting

### Frontend pods not starting
- Check logs: `kubectl logs -n hotcalls-$ENVIRONMENT <pod-name>`
- Verify image exists in ACR: `az acr repository show --name <acr-name> --image hotcalls-frontend:$IMAGE_TAG`

### 404 errors on API calls
- Ensure ingress paths are correct: `/api` should go to backend
- Check backend service is running: `kubectl get svc -n hotcalls-$ENVIRONMENT`

### CORS errors
- Verify CORS_ALLOWED_ORIGINS includes `https://app1.hotcalls.ai`
- Restart backend pods after updating secrets

### SSL/TLS issues
- Check if TLS secret exists: `kubectl get secret -n hotcalls-$ENVIRONMENT`
- Verify certificate is valid for `app1.hotcalls.ai`

## Environment-Specific Settings

### Development
- Set `DEBUG=True` for Django
- Use self-signed certificates or cert-manager with Let's Encrypt staging

### Production  
- Set `DEBUG=False` for Django
- Use production TLS certificates
- Scale replicas as needed:
  ```bash
  export FRONTEND_REPLICAS=3
  export REPLICAS=3  # for backend
  ```

## Updating the Frontend

To update the frontend after code changes:

1. Pull latest changes and rebuild:
   ```bash
   cd ../hotcalls-visual-prototype
   git pull
   bun run build
   ```

2. Build and push new image:
   ```bash
   export IMAGE_TAG=v1.0.1  # increment version
   docker build -t $ACR_LOGIN_SERVER/hotcalls-frontend:$IMAGE_TAG .
   docker push $ACR_LOGIN_SERVER/hotcalls-frontend:$IMAGE_TAG
   ```

3. Update deployment:
   ```bash
   cd ../hotcalls
   envsubst < k8s/frontend-deployment.yaml | kubectl apply -f -
   ```

## API Configuration in Frontend

The frontend should make API calls to `/api/...` (relative URLs). This will automatically route to the backend service through the ingress.

Example frontend API configuration:
```javascript
const API_BASE_URL = '/api';  // No need for full URL

fetch(`${API_BASE_URL}/users/`)
  .then(response => response.json())
  .then(data => console.log(data));
```

## Monitoring

Monitor your deployments:

```bash
# Watch pod status
kubectl get pods -n hotcalls-$ENVIRONMENT -w

# Check resource usage
kubectl top pods -n hotcalls-$ENVIRONMENT

# View logs
kubectl logs -f deployment/hotcalls-frontend -n hotcalls-$ENVIRONMENT
kubectl logs -f deployment/hotcalls-backend -n hotcalls-$ENVIRONMENT
``` 