#!/bin/bash
set -e

echo "Deploying to Kubernetes..."

# Set all variables
export ENVIRONMENT=dev
export ACR_LOGIN_SERVER=hotcallsdevelopmentneacrtc176s4q.azurecr.io
export IMAGE_TAG=latest
export REPLICAS=1
export RESOURCES_REQUESTS_MEMORY=128Mi
export RESOURCES_REQUESTS_CPU=100m
export RESOURCES_LIMITS_MEMORY=512Mi
export RESOURCES_LIMITS_CPU=500m
export CELERY_REPLICAS=1
export CELERY_RESOURCES_REQUESTS_MEMORY=64Mi
export CELERY_RESOURCES_REQUESTS_CPU=50m
export CELERY_RESOURCES_LIMITS_MEMORY=256Mi
export CELERY_RESOURCES_LIMITS_CPU=200m
export BEAT_RESOURCES_REQUESTS_MEMORY=32Mi
export BEAT_RESOURCES_REQUESTS_CPU=25m
export BEAT_RESOURCES_LIMITS_MEMORY=128Mi
export BEAT_RESOURCES_LIMITS_CPU=100m

# Apply ConfigMap
echo "Creating ConfigMap..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: hotcalls-config
  namespace: hotcalls-dev
data:
  ENVIRONMENT: "development"
  DEBUG: "False"
  ALLOWED_HOSTS: "*"
  CORS_ALLOWED_ORIGINS: "*"
  BASE_URL: "https://api.hotcalls.com"
  DJANGO_SETTINGS_MODULE: "hotcalls.settings.production"
EOF

# Apply Secrets
echo "Creating Secrets..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: hotcalls-secrets
  namespace: hotcalls-dev
type: Opaque
stringData:
  SECRET_KEY: "django-insecure-temporary-key-replace-in-production"
  DATABASE_URL: "postgresql://hotcallsadmin@hotcalls-development-ne-postgres:password@hotcalls-development-ne-postgres.postgres.database.azure.com:5432/hotcalls"
EOF

# Apply Service
echo "Creating Service..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: hotcalls-backend-service
  namespace: hotcalls-dev
spec:
  type: ClusterIP
  ports:
  - name: http
    port: 80
    targetPort: 8000
    protocol: TCP
  selector:
    app.kubernetes.io/name: hotcalls
    app.kubernetes.io/component: backend
EOF

# Apply Deployment
echo "Creating Deployment..."
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hotcalls-backend
  namespace: hotcalls-dev
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: hotcalls
      app.kubernetes.io/component: backend
  template:
    metadata:
      labels:
        app.kubernetes.io/name: hotcalls
        app.kubernetes.io/component: backend
    spec:
      containers:
      - name: backend
        image: ${ACR_LOGIN_SERVER}/hotcalls-backend:${IMAGE_TAG}
        ports:
        - name: http
          containerPort: 8000
        envFrom:
        - configMapRef:
            name: hotcalls-config
        - secretRef:
            name: hotcalls-secrets
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
EOF

# Apply Ingress
echo "Creating Ingress..."
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hotcalls-ingress
  namespace: hotcalls-dev
  annotations:
    kubernetes.io/ingress.class: azure/application-gateway
spec:
  rules:
  - host: api.hotcalls.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: hotcalls-backend-service
            port:
              number: 80
EOF

echo "Waiting for deployment..."
kubectl rollout status deployment/hotcalls-backend -n hotcalls-dev

echo "Deployment complete!"
kubectl get pods -n hotcalls-dev
kubectl get ingress -n hotcalls-dev 