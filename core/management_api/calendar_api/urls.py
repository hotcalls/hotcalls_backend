from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CalendarViewSet, CalendarConfigurationViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'calendars', CalendarViewSet, basename='calendar')
router.register(r'calendar-configurations', CalendarConfigurationViewSet, basename='calendarconfig')

urlpatterns = [
    path('', include(router.urls)),
] 