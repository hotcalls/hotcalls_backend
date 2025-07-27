# HotCalls Single-Stage Deployment

This document describes the simplified, single-stage deployment process for HotCalls that addresses the previous Terraform provider chicken-and-egg problems.

## Architecture Overview

The deployment has been refactored to eliminate the complex provider dependencies:

1. **Terraform Infrastructure Only**: Creates Azure resources (AKS, PostgreSQL, ACR, Storage) without Kubernetes provider
2. **Kubernetes Manifests**: Applied separately using `kubectl` with environment variable substitution
3. **Single Script**: `deploy.sh` orchestrates the entire process using your `.env` file

## Prerequisites

Before running the deployment, ensure you have:

- Azure CLI (`az`) installed and logged in
- Terraform (`terraform`) installed
- kubectl (`kubectl`) installed  
- Docker (`docker`) installed
- Git (`git`) installed
- `envsubst` utility (usually available on macOS/Linux)
- Node.js and npm (required if deploying frontend)

## Quick Start

1. **Ensure your `.env` file is properly configured**:
   ```bash
   # Your .env file should contain all required variables
   cp .env.example .env  # if you don't have .env yet
   ```

2. **(Optional) Configure frontend repository**:
   ```bash
   # Add to your .env file if you have a frontend
   echo "FRONTEND_REPO_URL=git@github.com:your-org/hotcalls-frontend.git" >> .env
   ```

3. **Run the deployment**:
   ```bash
   ./deploy.sh
   ```

4. **Wait for completion** - the script will:
   - Validate prerequisites and environment variables
   - Clone and build frontend (if configured)
   - Deploy Azure infrastructure with Terraform
   - Build and push Docker images to ACR
   - Configure kubectl for the AKS cluster
   - Deploy Kubernetes resources
   - Show the application URL

## Environment Variables

The deployment uses your `.env` file directly. Key variables:

### Required Variables
- `SECRET_KEY` - Django secret key
- `DB_USER` - PostgreSQL username 
- `DB_PASSWORD` - PostgreSQL password
- `DB_NAME` - Database name
- `REDIS_PASSWORD` - Redis password
- `EMAIL_HOST` - SMTP server
- `EMAIL_HOST_USER` - SMTP username
- `EMAIL_HOST_PASSWORD` - SMTP password

### Optional Variables
- `ENVIRONMENT` - Deployment environment (default: staging)
- `IMAGE_TAG` - Docker image tag (default: latest)
- `REPLICAS` - Number of replicas (default: 1)
- `FRONTEND_REPO_URL` - Private frontend repository URL (SSH format recommended)

## Frontend Deployment

### Automatic Frontend Handling

The deployment script now automatically handles frontend deployment:

1. **If `FRONTEND_REPO_URL` is set in `.env`**:
   - Clones the private repository to `frontend/` directory
   - Installs dependencies (`npm install` or `yarn install`)
   - Builds the project (`npm run build`)
   - Copies build output to `dist/` directory
   - Builds and pushes frontend Docker image

2. **If no frontend repository is configured**:
   - Skips frontend deployment
   - Only deploys backend services

### Private Repository Access

For private repositories, ensure:

1. **SSH Key Authentication** (recommended):
   ```bash
   # Generate SSH key if you don't have one
   ssh-keygen -t ed25519 -C "your_email@example.com"
   
   # Add to your GitHub account
   cat ~/.ssh/id_ed25519.pub
   
   # Test access
   ssh -T git@github.com
   
   # Use SSH URL in .env
   FRONTEND_REPO_URL=git@github.com:your-org/hotcalls-frontend.git
   ```

2. **HTTPS with Token** (alternative):
   ```bash
   # Use personal access token
   FRONTEND_REPO_URL=https://username:token@github.com/your-org/hotcalls-frontend.git
   ```

### Frontend Build Requirements

Your frontend repository should:

- Have a `package.json` file
- Support `npm run build` or `yarn build` command
- Output built files to either `dist/` or `build/` directory
- Be a standard React, Vue, or similar SPA application

### Frontend Directory Structure

After deployment, you'll have:
```
hotcalls/
├── frontend/          # Cloned frontend repository
│   ├── src/
│   ├── package.json
│   └── dist/         # or build/
├── dist/             # Copied build output for Docker
└── ...
```

## What's Different

### Fixed Issues
- ✅ **No Kubernetes provider in Terraform** - Eliminates chicken-and-egg problem
- ✅ **No PostgreSQL provider** - Avoids connection issues during planning
- ✅ **Uses your .env values directly** - No random password generation
- ✅ **LoadBalancer service** - Simple external access without Application Gateway
- ✅ **Environment variable substitution** - K8s manifests use envsubst
- ✅ **Proper dependency ordering** - Infrastructure → Images → Kubernetes

### Simplified Architecture
- **Terraform**: Only provisions Azure infrastructure
- **Kubernetes**: Deployed via kubectl with your exact .env values
- **Services**: LoadBalancer provides direct external IP
- **Redis**: Deployed as K8s pod (not external service)

## Deployment Process Details

### Phase 1: Infrastructure (Terraform)
```bash
cd terraform
terraform init
terraform plan -out=tfplan  
terraform apply tfplan
```

Creates:
- Resource Group
- Virtual Network with subnets
- AKS Cluster
- PostgreSQL Flexible Server (public access)
- Azure Container Registry
- Storage Account

### Phase 2: Container Images
```bash
az acr login --name <registry>
docker build -t <registry>/hotcalls-backend:latest .
docker push <registry>/hotcalls-backend:latest
```

### Phase 3: Kubernetes Deployment
```bash
cd k8s
envsubst < namespace.yaml | kubectl apply -f -
envsubst < secrets.yaml | kubectl apply -f -
# ... all manifests with environment substitution
```

Creates:
- Namespace: `hotcalls-${ENVIRONMENT}`
- Redis deployment with password auth
- Backend deployment with your settings
- LoadBalancer service for external access

## Accessing the Application

After deployment completes:

1. **Get the external IP**:
   ```bash
   kubectl get services -n hotcalls-staging
   ```

2. **Check application status**:
   ```bash
   kubectl get pods -n hotcalls-staging
   kubectl logs -f deployment/hotcalls-backend -n hotcalls-staging
   ```

3. **Access the application**:
   - The script will show: `Application URL: http://<external-ip>`
   - API: `http://<external-ip>/api/`
   - Admin: `http://<external-ip>/admin/`
   - Health: `http://<external-ip>/health/`

## Cleanup

To remove deployed resources:

```bash
# Clean up only Kubernetes resources (safe)
./cleanup.sh --kubernetes-only

# Clean up only frontend files
./cleanup.sh --frontend-only

# Clean up everything including infrastructure (destructive!)
./cleanup.sh --all
```

## Troubleshooting

### Common Issues

1. **Azure login required**:
   ```bash
   az login
   ```

2. **kubectl not configured**:
   ```bash
   az aks get-credentials --resource-group <rg> --name <cluster>
   ```

3. **Frontend clone failed**:
   ```bash
   # Test SSH access
   ssh -T git@github.com
   
   # Check repository URL
   echo $FRONTEND_REPO_URL
   
   # Verify you have access to the private repo
   ```

4. **Frontend build failed**:
   ```bash
   # Check Node.js version
   node --version
   npm --version
   
   # Build manually to see errors
   cd frontend
   npm install
   npm run build
   ```

5. **Image pull errors**:
   ```bash
   # Check if images were pushed
   az acr repository list --name <registry>
   ```

6. **LoadBalancer pending**:
   ```bash
   kubectl describe service hotcalls-backend-service -n hotcalls-staging
   ```

### Debug Commands

```bash
# Check all resources
kubectl get all -n hotcalls-staging

# Check logs
kubectl logs -f deployment/hotcalls-backend -n hotcalls-staging

# Check frontend logs (if deployed)
kubectl logs -f deployment/hotcalls-frontend -n hotcalls-staging

# Check secrets (base64 encoded)
kubectl get secret hotcalls-secrets -n hotcalls-staging -o yaml

# Check configuration
kubectl get configmap hotcalls-config -n hotcalls-staging -o yaml

# Port forward for local testing
kubectl port-forward service/hotcalls-backend-service 8080:80 -n hotcalls-staging
```

## Manual Steps (if needed)

If the automated script fails, you can run steps manually:

1. **Frontend only**:
   ```bash
   # Clone and build frontend
   git clone $FRONTEND_REPO_URL frontend
   cd frontend
   npm install
   npm run build
   cp -r dist ../ # or cp -r build ../dist
   cd ..
   ```

2. **Infrastructure only**:
   ```bash
   cd terraform
   # Set TF_VAR_* variables from .env
   terraform init && terraform apply
   ```

3. **Images only**:
   ```bash
   ACR_NAME=$(cd terraform && terraform output -raw acr_login_server)
   az acr login --name ${ACR_NAME%%.*}
   
   # Backend
   docker build -t $ACR_NAME/hotcalls-backend:latest .
   docker push $ACR_NAME/hotcalls-backend:latest
   
   # Frontend (if dist/ exists)
   docker build -f frontend-deploy/Dockerfile -t $ACR_NAME/hotcalls-frontend:latest .
   docker push $ACR_NAME/hotcalls-frontend:latest
   ```

4. **Kubernetes only**:
   ```bash
   # Get AKS credentials
   az aks get-credentials --resource-group <rg> --name <cluster>
   
   # Apply manifests
   cd k8s
   export ENVIRONMENT=staging
   export HAS_FRONTEND=true  # or false
   # ... set other env vars from .env ...
   for file in namespace.yaml rbac.yaml configmap.yaml secrets.yaml redis-deployment.yaml deployment.yaml service.yaml; do
     envsubst < $file | kubectl apply -f -
   done
   ```

## Environment-Specific Deployments

To deploy to different environments:

```bash
# Development
export ENVIRONMENT=dev
./deploy.sh

# Staging (default)
export ENVIRONMENT=staging  
./deploy.sh

# Production
export ENVIRONMENT=production
./deploy.sh
```

Each environment gets its own:
- Kubernetes namespace: `hotcalls-${ENVIRONMENT}`
- Resource naming: `hotcalls-${ENVIRONMENT}-*`

## Security Notes

- PostgreSQL uses public access with Azure firewall rules
- Secrets are stored as Kubernetes secrets (base64 encoded)
- Redis requires password authentication
- CORS is configured via environment variables
- No TLS/SSL termination (add NGINX ingress + cert-manager for production)

## Next Steps for Production

For production deployment, consider:

1. **TLS/SSL**: Add cert-manager and Let's Encrypt
2. **Private networking**: Use private endpoints for PostgreSQL
3. **Monitoring**: Add Prometheus/Grafana
4. **Backup**: Configure PostgreSQL backups
5. **Scaling**: Tune HPA settings
6. **Security**: Network policies, Pod security standards 