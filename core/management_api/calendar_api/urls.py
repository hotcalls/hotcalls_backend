"""URL configuration for Calendar API"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarViewSet

# Create router for calendar endpoints
router = DefaultRouter()
router.register(r'', CalendarViewSet, basename='calendar')

urlpatterns = router.urls