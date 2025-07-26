"""
URL configuration for HotCalls project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView, 
    SpectacularRedocView, 
    SpectacularSwaggerView
)
from core.health import health_check, readiness_check, startup_check

# API URL patterns
api_patterns = [
    # Management API endpoints (following user preference for management_api folder)
    path('users/', include('core.management_api.user_api.urls')),
    path('subscriptions/', include('core.management_api.subscription_api.urls')),
    path('workspaces/', include('core.management_api.workspace_api.urls')),
    path('agents/', include('core.management_api.agent_api.urls')),
    path('leads/', include('core.management_api.lead_api.urls')),
    path('calls/', include('core.management_api.call_api.urls')),
    path('calendars/', include('core.management_api.calendar_api.urls')),
    path('voice/', include('core.management_api.voice_api.urls')),
    
    # OpenAPI schema and documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Health check patterns (for Kubernetes probes)
health_patterns = [
    path('health/', health_check, name='health-check'),
    path('ready/', readiness_check, name='readiness-check'),
    path('startup/', startup_check, name='startup-check'),
]

# Main URL patterns
urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # Health checks (no versioning as per user preference)
    path('', include(health_patterns)),
    
    # API endpoints (no versioning as per user preference)
    path('api/', include(api_patterns)),
    
    # Django health check (additional health checks)
    path('health/', include('health_check.urls')),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Add debug toolbar URLs if available
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass
