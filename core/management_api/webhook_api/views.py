import json
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from core.models import WebhookLeadSource, LeadFunnel, Workspace
from core.services import WebhookLeadService
from .serializers import (
    WebhookLeadIncomeRequestSerializer,
    WebhookCreateRequestSerializer,
    WebhookCreateResponseSerializer,
    WebhookDeleteRequestSerializer,
    WebhookDeleteResponseSerializer,
    WebhookGetRequestSerializer,
    WebhookGetResponseSerializer,
    WebhookRefreshTokenRequestSerializer,
    WebhookRefreshTokenResponseSerializer,
    WebhookLeadIncomeResponseSerializer
)

logger = logging.getLogger(__name__)

class WebhookViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Create webhook",
        description="Creates a webhook with an associated lead funnel, returns the data needed to use the webhook",
        request=WebhookCreateRequestSerializer,
        responses={
            201: WebhookCreateResponseSerializer,
            400: {'description': 'Bad Request - Invalid input data'},
            403: {'description': 'Forbidden - User does not have access to workspace'},
            404: {'description': 'Not Found - Workspace does not exist'}
        }
    )
    @action(detail=False, methods=['post'], url_path='create')
    def create_webhook(self, request):
        """Create webhook with lead funnel and variables"""
        serializer = WebhookCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace_id = serializer.validated_data['workspace_id']
        webhook_name = serializer.validated_data['webhook_name']
        variables = serializer.validated_data.get('variables', [])

        # Check if workspace exists
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return Response({'error': 'Workspace not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access to workspace
        if request.user not in workspace.users.all() and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        # Create lead funnel with pattern "Funnel_<WebhookName>"
        funnel_name = f"Funnel_{webhook_name}"
        funnel = LeadFunnel.objects.create(
            name=funnel_name,
            workspace=workspace,
            is_active=True,
            custom_variables=variables
        )

        # Create webhook lead source
        source = WebhookLeadSource.objects.create(
            workspace=workspace,
            lead_funnel=funnel,
            name=webhook_name
        )

        # Build webhook URL
        base = settings.BASE_URL
        webhook_url = f"{base}/api/webhooks/leads/{source.public_key}/"

        # Prepare response data
        response_data = {
            'webhook_id': source.id,
            'webhook_name': source.name,
            'lead_funnel_id': funnel.id,
            'webhook_url': webhook_url,
            'secret_token': source.token,
            'public_key': source.public_key,
            'required_headers': {'Authorization': 'Bearer <token>'}
        }

        response_serializer = WebhookCreateResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Delete webhook",
        description="Deletes a webhook and its associated lead funnel",
        request=WebhookDeleteRequestSerializer,
        responses={
            200: WebhookDeleteResponseSerializer,
            400: {'description': 'Bad Request - Invalid input data'},
            403: {'description': 'Forbidden - User does not have access to workspace'},
            404: {'description': 'Not Found - Workspace or webhook does not exist'}
        }
    )
    @action(detail=False, methods=['delete'], url_path='delete')
    def delete_webhook(self, request):
        """Delete webhook and its associated lead funnel"""
        serializer = WebhookDeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace_id = serializer.validated_data['workspace_id']
        webhook_id = serializer.validated_data['webhook_id']

        # Check if workspace exists
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            response_data = {
                'status': 'error',
                'message': 'Workspace not found'
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access to workspace
        if request.user not in workspace.users.all() and not (request.user.is_staff or request.user.is_superuser):
            response_data = {
                'status': 'error',
                'message': 'Forbidden'
            }
            return Response(response_data, status=status.HTTP_403_FORBIDDEN)

        # Check if webhook exists
        try:
            webhook = WebhookLeadSource.objects.get(id=webhook_id, workspace=workspace)
        except WebhookLeadSource.DoesNotExist:
            response_data = {
                'status': 'error',
                'message': 'Webhook not found'
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)

        # Save webhook name for response message
        webhook_name = webhook.name

        try:
            # If funnel exists, delete it first (this will cascade delete the webhook due to OneToOneField)
            if hasattr(webhook, 'lead_funnel') and webhook.lead_funnel:
                with transaction.atomic():
                    funnel = webhook.lead_funnel
                    funnel.delete()  # This should cascade delete the webhook
            else:
                with transaction.atomic():
                    webhook.delete()

            response_data = {
                'status': 'success',
                'message': f'Webhook {webhook_name} has been deleted'
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error deleting webhook {webhook_id}: {str(e)}")
            response_data = {
                'status': 'error',
                'message': f'Webhook {webhook_name} was not deleted'
            }
            return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="Get webhook information",
        description="Retrieves detailed information about a webhook",
        request=WebhookGetRequestSerializer,
        responses={
            200: WebhookGetResponseSerializer,
            400: {'description': 'Bad Request - Invalid input data'},
            403: {'description': 'Forbidden - User does not have access to workspace'},
            404: {'description': 'Not Found - Workspace or webhook does not exist'}
        }
    )
    @action(detail=False, methods=['get'], url_path='get')
    def get_webhook(self, request):
        """Get webhook information"""
        serializer = WebhookGetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace_id = serializer.validated_data['workspace_id']
        webhook_id = serializer.validated_data['webhook_id']

        # Check if workspace exists
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return Response({'error': 'Workspace not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access to workspace
        if request.user not in workspace.users.all() and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        # Check if webhook exists
        try:
            webhook = WebhookLeadSource.objects.get(id=webhook_id, workspace=workspace)
        except WebhookLeadSource.DoesNotExist:
            return Response({'error': 'Webhook not found'}, status=status.HTTP_404_NOT_FOUND)

        # Prepare response data
        response_data = {
            'webhook_name': webhook.name,
            'webhook_id': webhook.id,
            'public_key': webhook.public_key,
            'token': webhook.token,
            'has_lead_funnel': hasattr(webhook, 'lead_funnel') and webhook.lead_funnel is not None
        }

        response_serializer = WebhookGetResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Refresh webhook token",
        description="Generates a new secure token for the webhook",
        request=WebhookRefreshTokenRequestSerializer,
        responses={
            200: WebhookRefreshTokenResponseSerializer,
            400: {'description': 'Bad Request - Invalid input data'},
            403: {'description': 'Forbidden - User does not have access to workspace'},
            404: {'description': 'Not Found - Workspace or webhook does not exist'}
        }
    )
    @action(detail=False, methods=['post'], url_path='refresh_token')
    def refresh_token(self, request):
        """Refresh webhook token by generating a new secure token"""
        serializer = WebhookRefreshTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace_id = serializer.validated_data['workspace_id']
        webhook_id = serializer.validated_data['webhook_id']

        # Check if workspace exists
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return Response({'error': 'Workspace not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access to workspace
        if request.user not in workspace.users.all() and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        # Check if webhook exists
        try:
            webhook = WebhookLeadSource.objects.get(id=webhook_id, workspace=workspace)
        except WebhookLeadSource.DoesNotExist:
            return Response({'error': 'Webhook not found'}, status=status.HTTP_404_NOT_FOUND)

        # Generate new token
        from secrets import token_urlsafe
        webhook.token = token_urlsafe(48)
        webhook.save(update_fields=['token', 'updated_at'])

        # Prepare response data
        response_data = {
            'webhook_id': webhook.id,
            'token': webhook.token
        }

        response_serializer = WebhookRefreshTokenResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=status.HTTP_200_OK)




@method_decorator(csrf_exempt, name='dispatch')
class WebhookInboundView(viewsets.ViewSet):
    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        summary="Receive inbound lead from webhook",
        description="Receives and processes an inbound lead from a webhook",
        request=WebhookLeadIncomeRequestSerializer,
        responses={
            200: WebhookLeadIncomeResponseSerializer,
            400: {'description': 'Bad Request - Invalid input data'},
            401: {'description': 'Unauthorized - Invalid token'},
            404: {'description': 'Not Found - Webhook does not exist'}
        },
        auth=None
    )
    def post(self, request, public_key: str = None):
        """Process inbound lead from webhook"""
        # Resolve webhook by public_key
        try:
            webhook = WebhookLeadSource.objects.select_related('lead_funnel', 'workspace', 'lead_funnel__agent').get(public_key=public_key)
        except WebhookLeadSource.DoesNotExist:
            response_data = {
                'status': 'error',
                'message': 'Unknown webhook'
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)

        # Authorization: Bearer token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        prefix = 'Bearer '
        if not auth_header.startswith(prefix):
            response_data = {
                'status': 'error',
                'message': 'Missing or invalid Authorization header'
            }
            return Response(response_data, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header[len(prefix):].strip()
        if token != webhook.token:
            response_data = {
                'status': 'error',
                'message': 'Invalid token'
            }
            return Response(response_data, status=status.HTTP_401_UNAUTHORIZED)

        # Validate request data
        serializer = WebhookLeadIncomeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Filter variables against allowed custom variables in funnel
        funnel_variables = webhook.lead_funnel.custom_variables or []
        filtered_variables = {}
        given_variables = serializer.validated_data.get('variables', {})

        for key, value in given_variables.items():
            if key in funnel_variables:
                filtered_variables[key] = value

        # Prepare lead data for service
        lead_data = {
            'name': serializer.validated_data['name'],
            'surname': serializer.validated_data['surname'],
            'email': serializer.validated_data['email'],
            'phone_number': serializer.validated_data['phone_number'],
            'custom_variables': filtered_variables
        }

        # Process lead using service
        service = WebhookLeadService()
        result = service.process_incoming_lead(lead_data, webhook)

        if result.get('status') == 'processed_with_agent':
            response_data = {
                'status': 'success',
                'message': f'Lead processed successfully for webhook {webhook.name}'
            }
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            response_data = {
                'status': 'error',
                'message': f'Lead was not processed: {result.get("status", "unknown error")}'
            }
            return Response(response_data, status=status.HTTP_200_OK)
