from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EventTypeViewSet

router = DefaultRouter()
# Workspace-scoped: /api/event-types/{workspace_id}/event-types/
router.register(r'(?P<workspace_id>[^/.]+)/event-types', EventTypeViewSet, basename='workspace-event-types')

urlpatterns = [
    path('', include(router.urls)),
]


