"""
URL configuration for project.
"""

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from .health import health_check, readiness_check, startup_check
from core.utils import CORSMediaView
from core.views import invitation_detail, accept_invitation


# Create public versions of documentation views
class PublicSpectacularAPIView(SpectacularAPIView):
    permission_classes = [AllowAny]


# Swagger API view. Currently public and allowed for any user
class PublicSpectacularSwaggerView(SpectacularSwaggerView):
    permission_classes = [AllowAny]


# Redoc API view. Currently public and allowed for any user
class PublicSpectacularRedocView(SpectacularRedocView):
    permission_classes = [AllowAny]


@csrf_exempt
@permission_classes([AllowAny])
def api_root(request):
    """API root endpoint that lists available API endpoints"""
    return JsonResponse(
        {
            "message": "HotCalls API v1",
            "endpoints": {
                "auth": "/api/auth/",
                "users": "/api/users/",
                "invitations": "/invitations/",
                "workspaces": "/api/workspaces/",
                "agents": "/api/agents/",
                "leads": "/api/leads/",
                "calls": "/api/calls/",
                "funnels": "/api/funnels/",
                "event-types": "/api/event-types/",
                "calendars": "/api/calendars/",
                "google-calendar": "/api/google-calendar/",
                "outlook-calendar": "/api/outlook-calendar/",
                "voices": "/api/voices/",
                "knowledge": "/api/knowledge/",
                "communication": "/api/communication/",
                "webhooks": "/api/webhooks/",
                "meta": "/api/meta/",
                "meta-integration": "/api/integrations/meta/",
                "jambonz-integration": "/api/integrations/jambonz/",
                "plans": "/api/plans/",
                "payments": "/api/payments/",
                "docs": "/api/docs/",
                "schema": "/api/schema/",
            },
        }
    )


urlpatterns = [
    # Admin interface. Currently blocked by kubernetes ingress configuration
    path("asdoksifje/admin/", admin.site.urls),
    # Multiple health checks. Currently used by kubernetes to evaluate deployment success
    path("health/", health_check, name="health_check"),
    path("health/readiness/", readiness_check, name="readiness_check"),
    path("health/startup/", startup_check, name="startup_check"),
    path("api/", api_root, name="api-root"),
    path("api/schema/", PublicSpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        PublicSpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        PublicSpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    path(
        "api/auth/",
        include(
            ("core.management_api.auth_api.urls", "auth_api"),
            namespace="auth_api",
        ),
    ),
    path(
        "api/users/",
        include(
            ("core.management_api.user_api.urls", "user_api"),
            namespace="user_api",
        ),
    ),
    path(
        "api/payments/",
        include(
            ("core.management_api.payment_api.urls", "payment_api"),
            namespace="payment_api",
        ),
    ),
    path(
        "api/plans/",
        include(
            ("core.management_api.plan_api.urls", "plan_api"),
            namespace="plan_api",
        ),
    ),
    path(
        "api/workspaces/",
        include(
            ("core.management_api.workspace_api.urls", "workspace_api"),
            namespace="workspace_api",
        ),
    ),
    path(
        "api/agents/",
        include(
            ("core.management_api.agent_api.urls", "agent_api"),
            namespace="agent_api",
        ),
    ),
    path(
        "api/leads/",
        include(
            ("core.management_api.lead_api.urls", "lead_api"),
            namespace="lead_api",
        ),
    ),
    path(
        "api/calls/",
        include(
            ("core.management_api.call_api.urls", "call_api"),
            namespace="call_api",
        ),
    ),
    path(
        "api/funnels/",
        include(
            ("core.management_api.funnel_api.urls", "funnel_api"),
            namespace="funnel_api",
        ),
    ),
    path(
        "api/event-types/",
        include(
            ("core.management_api.event_type_api.urls", "event_type_api"),
            namespace="event_type_api",
        ),
    ),
    path(
        "api/calendars/",
        include(
            ("core.management_api.calendar_api.urls", "calendar_api"),
            namespace="calendar_api",
        ),
    ),
    path(
        "api/google-calendar/",
        include(
            ("core.management_api.google_calendar_api.urls", "google_calendar_api"),
            namespace="google_calendar_api",
        ),
    ),
    path(
        "api/outlook-calendar/",
        include(
            ("core.management_api.outlook_calendar_api.urls", "outlook_calendar_api"),
            namespace="outlook_calendar_api",
        ),
    ),
    path(
        "api/communication/",
        include(
            ("core.management_api.communication_api.urls", "communication_api"),
            namespace="communication_api",
        ),
    ),
    path(
        "api/voices/",
        include(
            ("core.management_api.voice_api.urls", "voice_api"), namespace="voice_api"
        ),
    ),
    path(
        "api/meta/",
        include(
            ("core.management_api.meta_api.urls", "meta_api"), namespace="meta_api"
        ),
    ),
    path(
        "api/knowledge/",
        include(
            ("core.management_api.knowledge_api.urls", "knowledge_api"),
            namespace="knowledge_api",
        ),
    ),
    path(
        "api/integrations/meta/",
        include(
            ("core.management_api.meta_api.webhook_urls", "meta_webhooks"),
            namespace="meta_webhooks",
        ),
    ),
    path(
        "api/integrations/jambonz/",
        include(
            ("core.management_api.jambonz_api.urls", "jambonz_webhooks"),
            namespace="jambonz_webhooks",
        ),
    ),
    path(
        "api/webhooks/",
        include(
            ("core.management_api.webhook_api.urls", "webhook_api"),
            namespace="webhook_api",
        ),
    ),
    path("invitations/<str:token>/", invitation_detail, name="invitation_detail"),
    path(
        "invitations/<str:token>/accept/", accept_invitation, name="accept_invitation"
    ),
]

# Add Django Debug Toolbar URLs in development
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include('debug_toolbar.urls')),
        ] + urlpatterns
    except ImportError:
        pass
