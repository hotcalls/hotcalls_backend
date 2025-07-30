# NGINX Ingress Controller
resource "helm_release" "nginx_ingress" {
  name       = "ingress-nginx"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  namespace  = "ingress-nginx"
  
  create_namespace = true
  
  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }
  
  set {
    name  = "controller.service.annotations.service\\.beta\\.kubernetes\\.io/azure-load-balancer-health-probe-request-path"
    value = "/healthz"
  }
  
  # Configure nginx to handle large file uploads (1GB max)
  set {
    name  = "controller.config.proxy-body-size"
    value = "1024m"
  }
  
  # Increase client body buffer size for better performance with large uploads
  set {
    name  = "controller.config.client-body-buffer-size"
    value = "100m"
  }
  
  # Increase timeouts for large file uploads
  set {
    name  = "controller.config.proxy-connect-timeout"
    value = "600"
  }
  
  set {
    name  = "controller.config.proxy-send-timeout"
    value = "600"
  }
  
  set {
    name  = "controller.config.proxy-read-timeout"
    value = "600"
  }
}

# Kubernetes Namespace
resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace_name
    
    labels = {
      environment = var.environment
      app         = "hotcalls"
    }
  }
  
  depends_on = [helm_release.nginx_ingress]
}

# Application Secrets
resource "kubernetes_secret" "app_secrets" {
  metadata {
    name      = "hotcalls-secrets"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    SECRET_KEY                   = var.secret_key
    ALLOWED_HOSTS               = "*"
    DB_NAME                     = var.db_name
    DB_USER                     = var.db_user
    DB_PASSWORD                 = var.db_password
    DB_HOST                     = var.db_host
    REDIS_HOST                  = "redis-service"
    REDIS_PORT                  = "6379"
    REDIS_DB                    = "0"
    REDIS_PASSWORD              = var.redis_password
    CELERY_BROKER_URL           = "redis://redis-service:6379/0"
    CELERY_RESULT_BACKEND       = "redis://redis-service:6379/0"
    AZURE_ACCOUNT_NAME          = var.storage_account_name
    AZURE_STORAGE_KEY           = var.storage_account_key
    EMAIL_BACKEND               = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST                  = var.email_host
    EMAIL_PORT                  = var.email_port
    EMAIL_USE_TLS               = var.email_use_tls
    EMAIL_USE_SSL               = var.email_use_ssl
    EMAIL_HOST_USER             = var.email_host_user
    EMAIL_HOST_PASSWORD         = var.email_host_password
    DEFAULT_FROM_EMAIL          = var.default_from_email
    SERVER_EMAIL                = var.server_email
    DEBUG                       = var.debug
    CORS_ALLOW_ALL_ORIGINS      = var.cors_allow_all_origins
    AZURE_CUSTOM_DOMAIN         = ""
    AZURE_KEY_VAULT_URL         = ""
    AZURE_CLIENT_ID             = ""
    AZURE_MONITOR_CONNECTION_STRING = ""
    BASE_URL                    = var.base_url
    DJANGO_SETTINGS_MODULE      = "hotcalls.settings.production"
  }

  type = "Opaque"
}

# ConfigMap for application configuration
resource "kubernetes_config_map" "app_config" {
  metadata {
    name      = "hotcalls-config"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    ENVIRONMENT   = var.environment
    DEBUG         = "False"
    TIME_ZONE     = "Europe/Berlin"
    DB_ENGINE     = "django.db.backends.postgresql"
    DB_PORT       = "5432"
    DB_SSLMODE    = "require"
    REDIS_PORT    = "6379"
    REDIS_DB      = "0"
    AZURE_STATIC_CONTAINER = "static"
    AZURE_MEDIA_CONTAINER  = "media"
    SECURE_SSL_REDIRECT    = "False"
    SESSION_COOKIE_SECURE  = "False"
    CSRF_COOKIE_SECURE     = "False"
    LOG_LEVEL     = "INFO"
  }
}

# Redis Deployment
resource "kubernetes_deployment" "redis" {
  metadata {
    name      = "redis"
    namespace = kubernetes_namespace.app.metadata[0].name
    
    labels = {
      app = "redis"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "redis"
      }
    }

    template {
      metadata {
        labels = {
          app = "redis"
        }
      }

      spec {
        container {
          name  = "redis"
          image = "redis:7-alpine"
          
          command = ["redis-server", "--requirepass", var.redis_password]
          
          port {
            container_port = 6379
          }
          
          resources {
            requests = {
              memory = "128Mi"
              cpu    = "100m"
            }
            limits = {
              memory = "256Mi"
              cpu    = "200m"
            }
          }
        }
      }
    }
  }
}

# Redis Service
resource "kubernetes_service" "redis" {
  metadata {
    name      = "redis-service"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    selector = {
      app = "redis"
    }

    port {
      port        = 6379
      target_port = 6379
    }
  }
}

# Backend Deployment
resource "kubernetes_deployment" "backend" {
  metadata {
    name      = "hotcalls-backend"
    namespace = kubernetes_namespace.app.metadata[0].name
    
    labels = {
      app = "hotcalls-backend"
    }
  }

  spec {
    replicas = var.backend_replicas

    selector {
      match_labels = {
        app = "hotcalls-backend"
      }
    }

    template {
      metadata {
        labels = {
          app = "hotcalls-backend"
        }
      }

      spec {
        container {
          name  = "backend"
          image = "${var.container_registry}/hotcalls-backend:${var.image_tag}"
          
          port {
            container_port = 8000
          }
          
          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_config.metadata[0].name
            }
          }
          
          env_from {
            secret_ref {
              name = kubernetes_secret.app_secrets.metadata[0].name
            }
          }
          
          resources {
            requests = {
              memory = "512Mi"
              cpu    = "250m"
            }
            limits = {
              memory = "1Gi"
              cpu    = "500m"
            }
          }
          
          liveness_probe {
            http_get {
              path = "/health/"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }
          
          readiness_probe {
            http_get {
              path = "/health/"
              port = 8000
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }

  depends_on = [kubernetes_secret.app_secrets, kubernetes_config_map.app_config]
}

# Backend Service
resource "kubernetes_service" "backend" {
  metadata {
    name      = "hotcalls-backend-service"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    selector = {
      app = "hotcalls-backend"
    }

    port {
      port        = 80
      target_port = 8000
    }
  }
}

# Frontend Deployment
resource "kubernetes_deployment" "frontend" {
  metadata {
    name      = "hotcalls-frontend"
    namespace = kubernetes_namespace.app.metadata[0].name
    
    labels = {
      app = "hotcalls-frontend"
    }
  }

  spec {
    replicas = var.frontend_replicas

    selector {
      match_labels = {
        app = "hotcalls-frontend"
      }
    }

    template {
      metadata {
        labels = {
          app = "hotcalls-frontend"
        }
      }

      spec {
        container {
          name  = "frontend"
          image = "${var.container_registry}/hotcalls-frontend:${var.image_tag}"
          
          port {
            container_port = 8080
          }
          
          resources {
            requests = {
              memory = "128Mi"
              cpu    = "100m"
            }
            limits = {
              memory = "256Mi"
              cpu    = "200m"
            }
          }
        }
      }
    }
  }
}

# Frontend Service
resource "kubernetes_service" "frontend" {
  metadata {
    name      = "hotcalls-frontend-service"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    selector = {
      app = "hotcalls-frontend"
    }

    port {
      port        = 80
      target_port = 8080
    }
  }
}

# Ingress for routing
resource "kubernetes_ingress_v1" "app" {
  metadata {
    name      = "hotcalls-ingress"
    namespace = kubernetes_namespace.app.metadata[0].name
    
    annotations = {
      "kubernetes.io/ingress.class"                = "nginx"
      "nginx.ingress.kubernetes.io/rewrite-target" = "/$2"
      "nginx.ingress.kubernetes.io/use-regex"      = "true"
    }
  }

  spec {
    rule {
      http {
        # API routes to backend
        path {
          path      = "/api(/|$)(.*)"
          path_type = "Prefix"
          
          backend {
            service {
              name = kubernetes_service.backend.metadata[0].name
              port {
                number = 80
              }
            }
          }
        }
        
        # Frontend routes
        path {
          path      = "/(.*)"
          path_type = "Prefix"
          
          backend {
            service {
              name = kubernetes_service.frontend.metadata[0].name
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }

  depends_on = [kubernetes_service.backend, kubernetes_service.frontend, helm_release.nginx_ingress]
} 