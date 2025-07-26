#!/bin/bash

# Dynamic Kubernetes Deployment Script
# Usage: ./deploy.sh [dev|staging|prod]

set -e

# Default environment
ENVIRONMENT=${1:-dev}

# Environment-specific configurations
case $ENVIRONMENT in
  "dev")
    # Development - Small, cheap resources
    export REPLICAS=1
    export CELERY_REPLICAS=1
    export IMAGE_TAG="latest"
    
    # Backend resources
    export RESOURCES_REQUESTS_CPU="100m"
    export RESOURCES_REQUESTS_MEMORY="128Mi"
    export RESOURCES_LIMITS_CPU="500m"
    export RESOURCES_LIMITS_MEMORY="512Mi"
    
    # Celery worker resources
    export CELERY_RESOURCES_REQUESTS_CPU="50m"
    export CELERY_RESOURCES_REQUESTS_MEMORY="64Mi"
    export CELERY_RESOURCES_LIMITS_CPU="200m"
    export CELERY_RESOURCES_LIMITS_MEMORY="256Mi"
    
    # Celery beat resources
    export BEAT_RESOURCES_REQUESTS_CPU="25m"
    export BEAT_RESOURCES_REQUESTS_MEMORY="32Mi"
    export BEAT_RESOURCES_LIMITS_CPU="100m"
    export BEAT_RESOURCES_LIMITS_MEMORY="128Mi"
    
    # HPA settings
    export HPA_MIN_REPLICAS=1
    export HPA_MAX_REPLICAS=2
    export CELERY_HPA_MIN_REPLICAS=1
    export CELERY_HPA_MAX_REPLICAS=2
    
    # Config settings
    export DEBUG="True"
    export DB_SSLMODE="prefer"
    export SECURE_SSL_REDIRECT="False"
    export SESSION_COOKIE_SECURE="False"
    export CSRF_COOKIE_SECURE="False"
    export LOG_LEVEL="DEBUG"
    export DJANGO_LOG_LEVEL="DEBUG"
    ;;
  "staging")
    # Staging - Medium resources
    export REPLICAS=2
    export CELERY_REPLICAS=1
    export IMAGE_TAG="staging"
    
    # Backend resources
    export RESOURCES_REQUESTS_CPU="200m"
    export RESOURCES_REQUESTS_MEMORY="256Mi"
    export RESOURCES_LIMITS_CPU="1000m"
    export RESOURCES_LIMITS_MEMORY="1Gi"
    
    # Celery worker resources
    export CELERY_RESOURCES_REQUESTS_CPU="100m"
    export CELERY_RESOURCES_REQUESTS_MEMORY="128Mi"
    export CELERY_RESOURCES_LIMITS_CPU="500m"
    export CELERY_RESOURCES_LIMITS_MEMORY="512Mi"
    
    # Celery beat resources
    export BEAT_RESOURCES_REQUESTS_CPU="50m"
    export BEAT_RESOURCES_REQUESTS_MEMORY="64Mi"
    export BEAT_RESOURCES_LIMITS_CPU="200m"
    export BEAT_RESOURCES_LIMITS_MEMORY="256Mi"
    
    # HPA settings
    export HPA_MIN_REPLICAS=2
    export HPA_MAX_REPLICAS=5
    export CELERY_HPA_MIN_REPLICAS=1
    export CELERY_HPA_MAX_REPLICAS=3
    
    # Config settings
    export DEBUG="False"
    export DB_SSLMODE="require"
    export SECURE_SSL_REDIRECT="True"
    export SESSION_COOKIE_SECURE="True"
    export CSRF_COOKIE_SECURE="True"
    export LOG_LEVEL="INFO"
    export DJANGO_LOG_LEVEL="INFO"
    ;;
  "prod")
    # Production - Large resources
    export REPLICAS=3
    export CELERY_REPLICAS=2
    export IMAGE_TAG="stable"
    
    # Backend resources
    export RESOURCES_REQUESTS_CPU="500m"
    export RESOURCES_REQUESTS_MEMORY="512Mi"
    export RESOURCES_LIMITS_CPU="2000m"
    export RESOURCES_LIMITS_MEMORY="2Gi"
    
    # Celery worker resources
    export CELERY_RESOURCES_REQUESTS_CPU="200m"
    export CELERY_RESOURCES_REQUESTS_MEMORY="256Mi"
    export CELERY_RESOURCES_LIMITS_CPU="1000m"
    export CELERY_RESOURCES_LIMITS_MEMORY="1Gi"
    
    # Celery beat resources
    export BEAT_RESOURCES_REQUESTS_CPU="100m"
    export BEAT_RESOURCES_REQUESTS_MEMORY="128Mi"
    export BEAT_RESOURCES_LIMITS_CPU="500m"
    export BEAT_RESOURCES_LIMITS_MEMORY="512Mi"
    
    # HPA settings
    export HPA_MIN_REPLICAS=3
    export HPA_MAX_REPLICAS=20
    export CELERY_HPA_MIN_REPLICAS=2
    export CELERY_HPA_MAX_REPLICAS=10
    
    # Config settings
    export DEBUG="False"
    export DB_SSLMODE="require"
    export SECURE_SSL_REDIRECT="True"
    export SESSION_COOKIE_SECURE="True"
    export CSRF_COOKIE_SECURE="True"
    export LOG_LEVEL="INFO"
    export DJANGO_LOG_LEVEL="WARNING"
    ;;
  *)
    echo "❌ Invalid environment: $ENVIRONMENT"
    echo "Usage: $0 [dev|staging|prod]"
    exit 1
    ;;
esac

export ENVIRONMENT

echo "🚀 Deploying HotCalls to $ENVIRONMENT environment..."
echo "   Replicas: $REPLICAS"
echo "   Image Tag: $IMAGE_TAG"
echo "   Resources: ${RESOURCES_REQUESTS_CPU}/${RESOURCES_LIMITS_CPU} CPU, ${RESOURCES_REQUESTS_MEMORY}/${RESOURCES_LIMITS_MEMORY} Memory"
echo ""

# Apply manifests with environment variable substitution
echo "📦 Creating namespace..."
envsubst < namespace.yaml | kubectl apply -f -

echo "🔧 Creating ConfigMap..."
envsubst < configmap.yaml | kubectl apply -f -

echo "🔐 Creating Secrets..."
envsubst < secrets.yaml | kubectl apply -f -

echo "👥 Creating RBAC..."
envsubst < rbac.yaml | kubectl apply -f -

echo "🚀 Creating Deployments..."
envsubst < deployment.yaml | kubectl apply -f -

echo "🌐 Creating Services..."
envsubst < service.yaml | kubectl apply -f -

echo "📈 Creating HPA..."
envsubst < hpa.yaml | kubectl apply -f -

echo "🌍 Creating Ingress..."
envsubst < ingress.yaml | kubectl apply -f -

echo ""
echo "✅ Deployment to $ENVIRONMENT completed!"
echo "🔍 Check status with: kubectl get all -n hotcalls-$ENVIRONMENT" 