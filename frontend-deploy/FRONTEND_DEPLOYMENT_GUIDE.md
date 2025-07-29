# Frontend Deployment Guide for Hotcalls

The frontend is now fully integrated into the main deployment process! 🎉

## Quick Start

The main `deploy.sh` script now handles EVERYTHING, including frontend deployment:

```bash
./deploy.sh --project-name=hotcalls --environment=staging --branch=staging
```

That's it! The script will:
1. ✅ Build the frontend from `./frontend` directory
2. ✅ Create optimized Docker image
3. ✅ Push to Azure Container Registry
4. ✅ Deploy to Kubernetes

## Architecture Overview

- **Frontend**: React app served by NGINX at `/`
- **Backend**: Django API served at `/api/*`, `/admin/*`, `/health/*`
- **Both services**: Behind the same ingress on your configured domain

## Frontend Build Process

The deploy script automatically:
1. Checks for frontend directory at `./frontend`
2. Installs dependencies (prefers `bun`, falls back to `npm` or `yarn`)
3. Runs `bun run build` (or `npm run build`)
4. Copies the `dist/` output to project root
5. Builds Docker image with NGINX
6. Pushes to ACR and deploys to K8s

## Skipping Frontend Build

If you need to deploy only backend changes:

```bash
SKIP_FRONTEND=true ./deploy.sh --project-name=hotcalls --environment=staging
```

## Manual Frontend Deployment

If you need to deploy ONLY the frontend:

```bash
cd /Users/martinb/Documents/hotcalls
./frontend-deploy/deploy-frontend.sh
```

Note: You must set environment variables first:
```bash
export ENVIRONMENT=staging
export ACR_LOGIN_SERVER=<your-acr>.azurecr.io
```

## Frontend Configuration

### Environment Variables

The frontend uses Vite environment variables:
- `.env.development` - Local development
- `.env.production` - Production build (created during deployment)

### API Configuration

Update `VITE_API_BASE_URL` in the appropriate `.env` file:
```
VITE_API_BASE_URL=https://your-domain.com
```

## Troubleshooting

### Frontend not updating?

1. Check if the build succeeded:
   ```bash
   ls -la frontend/dist/
   ```

2. Force a fresh build:
   ```bash
   rm -rf frontend/dist frontend/node_modules
   ./deploy.sh --project-name=hotcalls --environment=staging --no-cache
   ```

3. Check pod status:
   ```bash
   kubectl get pods -n hotcalls-staging -l app.kubernetes.io/component=frontend
   ```

4. View frontend logs:
   ```bash
   kubectl logs -n hotcalls-staging -l app.kubernetes.io/component=frontend
   ```

### Build Errors?

1. Ensure you have Node.js or Bun installed
2. Check `frontend/package.json` exists
3. Try building locally first:
   ```bash
   cd frontend
   bun install
   bun run build
   ```

## File Structure

```
hotcalls/
├── frontend/               # React app source
│   ├── src/               # Source code
│   ├── public/            # Static assets
│   ├── dist/              # Build output (git ignored)
│   └── package.json       # Dependencies
├── frontend-deploy/       # Frontend deployment tools
│   ├── Dockerfile         # NGINX container
│   └── deploy-frontend.sh # Standalone deploy script
└── deploy.sh             # Main deploy script (handles everything!)
```

## Best Practices

1. **Always commit frontend changes** before deploying
2. **Test locally first**: `cd frontend && bun run dev`
3. **Use the main deploy script**: It handles everything automatically
4. **Check the ingress**: Both frontend and backend share the same domain

The frontend deployment is now seamless and integrated! 🚀 