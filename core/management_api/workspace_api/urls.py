from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkspaceViewSet, InvitationDetailView

# Create router and register viewsets
router = DefaultRouter()
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'invitations', InvitationDetailView, basename='invitation')

urlpatterns = [
    path('', include(router.urls)),
] 