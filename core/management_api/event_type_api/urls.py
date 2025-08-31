from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EventTypeViewSet

router = DefaultRouter()
# Workspace-scoped: /api/event-types/{workspace_id}/event-types/
router.register(r'(?P<workspace_id>[^/.]+)/event-types', EventTypeViewSet, basename='workspace-event-types')

urlpatterns = [
    path('', include(router.urls)),
    # Additional subaccounts listing route (function on same viewset)
    path('<uuid:workspace_id>/sub-accounts/', EventTypeViewSet.as_view({'get': 'list_subaccounts'}), name='workspace-subaccounts'),
    # Availability and booking routes on the same viewset
    path('<uuid:workspace_id>/event-types/<uuid:pk>/availability/', EventTypeViewSet.as_view({'get': 'availability'}), name='event-type-availability'),
    path('<uuid:workspace_id>/event-types/<uuid:pk>/book/', EventTypeViewSet.as_view({'post': 'book'}), name='event-type-book'),
]


