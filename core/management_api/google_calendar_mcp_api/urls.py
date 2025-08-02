from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GoogleCalendarMCPTokenViewSet

router = DefaultRouter()
router.register(r'tokens', GoogleCalendarMCPTokenViewSet, basename='google-calendar-mcp-tokens')

urlpatterns = [
    path('', include(router.urls)),
] 