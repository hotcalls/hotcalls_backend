"""URL configuration for Outlook Calendar API"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OutlookCalendarAuthViewSet, OutlookCalendarViewSet

# Create routers
auth_router = DefaultRouter()
auth_router.register(r'auth', OutlookCalendarAuthViewSet, basename='outlook-auth')

calendar_router = DefaultRouter()
calendar_router.register(r'calendars', OutlookCalendarViewSet, basename='outlook-calendars')

urlpatterns = [
    path('', include(auth_router.urls)),
    path('', include(calendar_router.urls)),
]
