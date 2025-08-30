from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from core.models import EventType, Workspace, SubAccount
from core.management_api.payment_api.permissions import IsWorkspaceMember
from .serializers import (
    EventTypeSerializer,
    EventTypeCreateUpdateSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List event types", tags=["Event Types"]),
    retrieve=extend_schema(summary="Get event type", tags=["Event Types"]),
    create=extend_schema(summary="Create event type", tags=["Event Types"]),
    partial_update=extend_schema(summary="Update event type", tags=["Event Types"]),
    destroy=extend_schema(summary="Delete event type", tags=["Event Types"]),
)
class EventTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    lookup_field = 'pk'

    def get_workspace(self) -> Workspace:
        workspace_id = self.kwargs.get('workspace_id') or self.request.query_params.get('workspace_id')
        return get_object_or_404(Workspace, id=workspace_id)

    def get_queryset(self):
        workspace = self.get_workspace()
        return EventType.objects.filter(workspace=workspace).order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EventTypeCreateUpdateSerializer
        return EventTypeSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['workspace'] = self.get_workspace()
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event_type = serializer.save()
        return Response(EventTypeSerializer(event_type).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        event_type = serializer.save()
        return Response(EventTypeSerializer(event_type).data)


