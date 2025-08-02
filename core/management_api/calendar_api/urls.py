from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarViewSet, CalendarConfigurationViewSet

# Create separate routers to avoid URL conflicts
calendar_router = DefaultRouter()
calendar_router.register(r'', CalendarViewSet, basename='calendar')

config_router = DefaultRouter()
config_router.register(r'', CalendarConfigurationViewSet, basename='calendar-configuration')

urlpatterns = [
    # Calendar configurations must come BEFORE the general calendar routes
    path('configurations/', include(config_router.urls)),
    path('', include(calendar_router.urls)),
] 