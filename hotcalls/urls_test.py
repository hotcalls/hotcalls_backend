"""
Minimal URL configuration for testing the test call endpoint
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.http import HttpResponse

def api_root(request):
    """API root endpoint that lists available API endpoints"""
    from django.http import JsonResponse
    return JsonResponse({
        "message": "HotCalls API v1 (Test Environment)",
        "note": "Some APIs disabled for testing (calendars, payments, subscriptions, meta)",
        "endpoints": {
            "auth": "/api/auth/",
            "users": "/api/users/",
            "workspaces": "/api/workspaces/",
            "agents": "/api/agents/",
            "leads": "/api/leads/",
            "calls": "/api/calls/",  # <-- Your new test_call endpoint is here!
            "voices": "/api/voices/",
            "docs": "/api/docs/",
            "schema": "/api/schema/"
        },
        "test_call_endpoint": {
            "url": "/api/calls/make_test_call/",
            "method": "POST",
            "description": "NEW: Test call endpoint with only agent_id required!"
        }
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Root
    path('api/', api_root, name='api-root'),
    
    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # Authentication API
    path('api/auth/', include('core.management_api.auth_api.urls')),
    
    # Management APIs (only those that work without external dependencies)
    path('api/users/', include(('core.management_api.user_api.urls', 'user_api'), namespace='user_api')),
    path('api/workspaces/', include(('core.management_api.workspace_api.urls', 'workspace_api'), namespace='workspace_api')),
    path('api/agents/', include(('core.management_api.agent_api.urls', 'agent_api'), namespace='agent_api')),
    path('api/leads/', include(('core.management_api.lead_api.urls', 'lead_api'), namespace='lead_api')),
    path('api/calls/', include(('core.management_api.call_api.urls', 'call_api'), namespace='call_api')),
    path('api/voices/', include(('core.management_api.voice_api.urls', 'voice_api'), namespace='voice_api')),
    
    # Temporarily commented out APIs that need external dependencies:
    # path('api/subscriptions/', include(('core.management_api.subscription_api.urls', 'subscription_api'), namespace='subscription_api')),  # Needs Stripe
    # path('api/calendars/', include(('core.management_api.calendar_api.urls', 'calendar_api'), namespace='calendar_api')),  # Needs Google APIs
    # path('api/payments/', include(('core.management_api.payment_api.urls', 'payment_api'), namespace='payment_api')),  # Needs Stripe
    # path('api/meta/', include(('core.management_api.meta_api.urls', 'meta_api'), namespace='meta_api')),  # Needs Meta APIs
    
    # Simple health check
    path('health/', lambda request: HttpResponse("OK")),
] 