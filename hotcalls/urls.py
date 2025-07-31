"""
URL configuration for HotCalls project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from core.health import health_check
from core.utils import CORSMediaView

# Create public versions of documentation views
class PublicSpectacularAPIView(SpectacularAPIView):
    permission_classes = [AllowAny]

class PublicSpectacularSwaggerView(SpectacularSwaggerView):
    permission_classes = [AllowAny]

class PublicSpectacularRedocView(SpectacularRedocView):
    permission_classes = [AllowAny]

@csrf_exempt
@permission_classes([AllowAny])
def api_root(request):
    """API root endpoint that lists available API endpoints"""
    return JsonResponse({
        "message": "HotCalls API v1",
        "endpoints": {
            "auth": "/api/auth/",
            "users": "/api/users/",
            "workspaces": "/api/workspaces/",
            "agents": "/api/agents/",
            "leads": "/api/leads/",
            "calls": "/api/calls/",
            "calendars": "/api/calendars/",
            "voices": "/api/voices/",
            "subscriptions": "/api/subscriptions/",
            "payments": "/api/payments/",
            "meta": "/api/meta/",
            "livekit": "/api/livekit/",
            "docs": "/api/docs/",
            "schema": "/api/schema/"
        }
    })

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # Health check
    path('health/', health_check, name='health_check'),
    path('health/', include('health_check.urls')),
    
    # API Root
    path('api/', api_root, name='api-root'),
    
    # API Documentation (PUBLIC)
    path('api/schema/', PublicSpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', PublicSpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', PublicSpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Authentication API - NEW: Email-based authentication with verification
    path('api/auth/', include('core.management_api.auth_api.urls')),
    
    # Management APIs - All require email verification
    path('api/users/', include(('core.management_api.user_api.urls', 'user_api'), namespace='user_api')),
    path('api/subscriptions/', include(('core.management_api.subscription_api.urls', 'subscription_api'), namespace='subscription_api')),
    path('api/workspaces/', include(('core.management_api.workspace_api.urls', 'workspace_api'), namespace='workspace_api')),
    path('api/agents/', include(('core.management_api.agent_api.urls', 'agent_api'), namespace='agent_api')),
    path('api/leads/', include(('core.management_api.lead_api.urls', 'lead_api'), namespace='lead_api')),
    path('api/calls/', include(('core.management_api.call_api.urls', 'call_api'), namespace='call_api')),
    # path('api/calendars/', include(('core.management_api.calendar_api.urls', 'calendar_api'), namespace='calendar_api')),

    path('api/voices/', include(('core.management_api.voice_api.urls', 'voice_api'), namespace='voice_api')),
    # path('api/payments/', include(('core.management_api.payment_api.urls', 'payment_api'), namespace='payment_api')),
    
    # Meta Integration Management API
    # path('api/meta/', include(('core.management_api.meta_api.urls', 'meta_api'), namespace='meta_api')),
    
    # LiveKit Token Management API (Superuser only)
    path('api/livekit/', include(('core.management_api.livekit_api.urls', 'livekit_api'), namespace='livekit_api')),
    
    # Meta Webhooks (for Meta to call)
    path('api/integrations/meta/', include('core.management_api.meta_api.webhook_urls')),
]

# Serve media files in development with CORS support
if settings.DEBUG:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', CORSMediaView.as_view(), name='media'),
    ]
