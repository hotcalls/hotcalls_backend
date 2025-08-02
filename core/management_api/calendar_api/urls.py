from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarViewSet, CalendarConfigurationViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'', CalendarViewSet, basename='calendar')
router.register(r'configurations', CalendarConfigurationViewSet, basename='calendarconfig')

urlpatterns = [
    path('', include(router.urls)),
] 