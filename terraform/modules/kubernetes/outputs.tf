# Namespace outputs
output "namespace_name" {
  description = "Name of the created namespace"
  value       = kubernetes_namespace.app.metadata[0].name
}

# Service outputs
output "backend_service_name" {
  description = "Name of the backend service"
  value       = kubernetes_service.backend.metadata[0].name
}

output "frontend_service_name" {
  description = "Name of the frontend service"
  value       = kubernetes_service.frontend.metadata[0].name
}

output "redis_service_name" {
  description = "Name of the Redis service"
  value       = kubernetes_service.redis.metadata[0].name
}

# Deployment outputs
output "backend_deployment_name" {
  description = "Name of the backend deployment"
  value       = kubernetes_deployment.backend.metadata[0].name
}

output "frontend_deployment_name" {
  description = "Name of the frontend deployment"
  value       = kubernetes_deployment.frontend.metadata[0].name
}

# Ingress outputs
output "ingress_name" {
  description = "Name of the ingress"
  value       = kubernetes_ingress_v1.app.metadata[0].name
} 