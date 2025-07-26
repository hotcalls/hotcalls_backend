from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkspaceViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')

urlpatterns = [
    path('', include(router.urls)),
] 