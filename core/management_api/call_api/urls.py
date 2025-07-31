from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CallLogViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'call-logs', CallLogViewSet, basename='calllog')

urlpatterns = [
    path('', include(router.urls)),
] 