"""URL configuration for Outlook Calendar API"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OutlookCalendarAuthViewSet, OutlookCalendarViewSet, OutlookSubAccountViewSet

# Create routers
auth_router = DefaultRouter()
auth_router.register(r'auth', OutlookCalendarAuthViewSet, basename='outlook-auth')

calendar_router = DefaultRouter()
calendar_router.register(r'calendars', OutlookCalendarViewSet, basename='outlook-calendars')

subaccount_router = DefaultRouter()
subaccount_router.register(r'sub-accounts', OutlookSubAccountViewSet, basename='outlook-subaccounts')

urlpatterns = [
    path('', include(auth_router.urls)),
    path('', include(calendar_router.urls)),
    path('', include(subaccount_router.urls)),
]
