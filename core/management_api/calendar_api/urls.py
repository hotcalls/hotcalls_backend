from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarViewSet, CalendarConfigurationViewSet, GoogleCalendarMCPTokenViewSet

# Create separate routers to avoid URL conflicts
calendar_router = DefaultRouter()
calendar_router.register(r'', CalendarViewSet, basename='calendar')

config_router = DefaultRouter()
config_router.register(r'', CalendarConfigurationViewSet, basename='calendar-configuration')

mcp_token_router = DefaultRouter()
mcp_token_router.register(r'', GoogleCalendarMCPTokenViewSet, basename='google-calendar-mcp-token')

urlpatterns = [
    # Calendar configurations must come BEFORE the general calendar routes
    path('configurations/', include(config_router.urls)),
    # MCP Token management (superuser only)
    path('mcp_tokens/', include(mcp_token_router.urls)),
    path('', include(calendar_router.urls)),
] 