# Frontend Deployment

This directory contains the Docker configuration for deploying the frontend application.

## Files

- `Dockerfile` - Multi-stage build for production nginx container
- `nginx.conf` - Nginx configuration optimized for React SPA

## How it works

1. The deployment script builds the frontend using `bun run build` or `npm run build`
2. The built files are copied to the project root as `dist/`
3. The Docker build copies `dist/` into the nginx container
4. Nginx serves the static files with SPA routing support

## Container Details

- **Base Image**: `nginx:alpine`
- **Port**: 8080 (non-privileged)
- **User**: nginx (non-root)
- **Health Check**: `/nginx-health` endpoint

## Features

- Gzip compression for better performance
- Long cache headers for static assets
- No cache for `index.html` to ensure updates
- Security headers
- SPA routing support (all routes fall back to `index.html`)