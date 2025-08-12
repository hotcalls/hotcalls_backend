import json
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from core.models import WebhookLeadSource, LeadFunnel, Workspace
from core.services import WebhookLeadService
from .serializers import (
    WebhookLeadPayloadSerializer,
    WebhookLeadSourceCreateSerializer,
    WebhookLeadSourceSerializer,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class WebhookInboundView(viewsets.ViewSet):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        summary="Inbound webhook for custom lead sources",
        request=WebhookLeadPayloadSerializer,
        auth=None
    )
    def post(self, request, public_key: str = None):
        # Resolve source
        try:
            source = WebhookLeadSource.objects.select_related('lead_funnel', 'workspace', 'lead_funnel__agent').get(public_key=public_key)
        except WebhookLeadSource.DoesNotExist:
            return Response({'error': 'Unknown webhook'}, status=status.HTTP_404_NOT_FOUND)

        # Authorization: Bearer token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        prefix = 'Bearer '
        if not auth_header.startswith(prefix):
            return Response({'error': 'Missing or invalid Authorization header'}, status=status.HTTP_401_UNAUTHORIZED)
        token = auth_header[len(prefix):].strip()
        if token != source.token:
            return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = WebhookLeadPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = WebhookLeadService()
        result = service.process_incoming_lead(serializer.validated_data, source)
        return Response(result, status=status.HTTP_200_OK)


class WebhookLeadSourceViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return WebhookLeadSource.objects.select_related('workspace', 'lead_funnel', 'lead_funnel__agent').all()
        return WebhookLeadSource.objects.select_related('workspace', 'lead_funnel', 'lead_funnel__agent').filter(workspace__in=user.mapping_user_workspaces.all())

    def get_serializer_class(self):
        if self.action == 'create':
            return WebhookLeadSourceCreateSerializer
        return WebhookLeadSourceSerializer

    @extend_schema(summary="Create a new webhook lead source", request=WebhookLeadSourceCreateSerializer)
    def create(self, request, *args, **kwargs):
        serializer = WebhookLeadSourceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace_id = serializer.validated_data['workspace']
        name = serializer.validated_data['name']

        # Validate workspace ownership
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return Response({'error': 'Workspace not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in workspace.users.all() and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        # Create funnel + source
        funnel = LeadFunnel.objects.create(name=name, workspace=workspace, is_active=True)
        source = WebhookLeadSource.objects.create(workspace=workspace, lead_funnel=funnel, name=name)

        # One-time show of token
        resp = {
            'id': str(source.id),
            'name': source.name,
            'lead_funnel': str(funnel.id),
            'url': WebhookLeadSourceSerializer(source, context={'request': request}).data['url'],
            'token': source.token,
            'required_headers': {'Authorization': 'Bearer <token>'},
            'created_at': source.created_at,
            'updated_at': source.updated_at,
        }
        return Response(resp, status=status.HTTP_201_CREATED)

    @extend_schema(summary="Rotate webhook token")
    @action(detail=True, methods=['post'])
    def rotate_token(self, request, pk=None):
        try:
            source = WebhookLeadSource.objects.get(pk=pk)
        except WebhookLeadSource.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.user not in source.workspace.users.all() and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        # rotate
        from secrets import token_urlsafe
        source.token = token_urlsafe(48)
        source.save(update_fields=['token', 'updated_at'])
        return Response({'token': source.token}, status=status.HTTP_200_OK)


