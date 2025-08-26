"""URL configuration for Google Calendar API"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GoogleCalendarAuthViewSet, GoogleCalendarViewSet, GoogleSubAccountViewSet

# Create routers
auth_router = DefaultRouter()
auth_router.register(r'auth', GoogleCalendarAuthViewSet, basename='google-auth')

calendar_router = DefaultRouter()
calendar_router.register(r'calendars', GoogleCalendarViewSet, basename='google-calendars')

subaccount_router = DefaultRouter()
subaccount_router.register(r'sub-accounts', GoogleSubAccountViewSet, basename='google-subaccounts')

urlpatterns = [
    path('', include(auth_router.urls)),
    path('', include(calendar_router.urls)),
    path('', include(subaccount_router.urls)),
]
