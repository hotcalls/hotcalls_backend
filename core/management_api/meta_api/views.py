from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from datetime import datetime
import logging
import json
import hmac
import hashlib

from core.models import MetaIntegration, MetaLeadForm, Lead, Workspace
from core.services.meta_integration import MetaIntegrationService
from .serializers import (
    MetaIntegrationSerializer, MetaIntegrationCreateSerializer,
    MetaLeadFormSerializer, MetaLeadFormCreateSerializer, MetaLeadFormBulkUpdateSerializer,
    MetaOAuthCallbackSerializer, MetaLeadWebhookSerializer,
    MetaWebhookVerificationSerializer, MetaLeadDataSerializer,
    MetaIntegrationStatsSerializer
)
from .filters import MetaIntegrationFilter, MetaLeadFormFilter
from .permissions import MetaIntegrationPermission, MetaWebhookPermission

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="📱 List Meta integrations",
        description="""
        Retrieve Meta (Facebook/Instagram) integrations for your workspaces.
        
        **🔐 Permission Requirements**:
        - User must be authenticated and email verified
        - Only integrations from user's workspaces are returned
        
        **🎯 Use Cases**:
        - Dashboard overview of Meta integrations
        - Integration management interface
        - Status monitoring
        """,
        responses={
            200: OpenApiResponse(
                response=MetaIntegrationSerializer(many=True),
                description="✅ Successfully retrieved Meta integrations"
            )
        }
    ),
    create=extend_schema(
        summary="📱 Create Meta integration", 
        description="Create new Meta integration for workspace (usually called after OAuth)"
    ),
)
class MetaIntegrationViewSet(viewsets.ModelViewSet):
    """ViewSet for Meta integrations CRUD management"""
    serializer_class = MetaIntegrationSerializer
    permission_classes = [MetaIntegrationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MetaIntegrationFilter
    search_fields = ['business_account_id', 'page_id']
    ordering_fields = ['created_at', 'updated_at', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by user's workspaces"""
        if self.request.user.is_staff or self.request.user.is_superuser:
            return MetaIntegration.objects.all()
        
        user_workspaces = self.request.user.mapping_user_workspaces.all()
        return MetaIntegration.objects.filter(workspace__in=user_workspaces)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return MetaIntegrationCreateSerializer
        return MetaIntegrationSerializer
    
    @extend_schema(
        summary="📊 Meta integration statistics",
        description="Get statistics for Meta integrations in your workspaces",
        responses={200: MetaIntegrationStatsSerializer}
    )
    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Get Meta integration statistics"""
        user_workspaces = request.user.mapping_user_workspaces.all()
        integrations = MetaIntegration.objects.filter(workspace__in=user_workspaces)
        
        stats = {
            'total_integrations': integrations.count(),
            'active_integrations': integrations.filter(status='active').count(),
            'total_lead_forms': MetaLeadForm.objects.filter(
                meta_integration__in=integrations
            ).count(),
            'total_leads_received': Lead.objects.filter(
                workspace__in=user_workspaces,
                integration_provider='meta'
            ).count(),
            'leads_this_month': Lead.objects.filter(
                workspace__in=user_workspaces,
                integration_provider='meta',
                created_at__month=timezone.now().month
            ).count(),
            'top_performing_forms': []  # TODO: Implement top performing forms logic
        }
        
        serializer = MetaIntegrationStatsSerializer(data=stats)
        serializer.is_valid()
        return Response(serializer.data)
    
    @extend_schema(
        summary="🔗 Get Meta OAuth URL",
        description="Get the OAuth URL to redirect user to Meta for authorization",
        responses={200: {'type': 'object', 'properties': {'oauth_url': {'type': 'string'}}}}
    )
    @action(detail=False, methods=['post'], url_path='get-oauth-url')
    def get_oauth_url(self, request):
        """Get OAuth URL for Meta authorization - FULLY AUTOMATED"""
        try:
            # Get workspace from request data
            workspace_id = request.data.get('workspace_id')
            if not workspace_id:
                return Response(
                    {'error': 'workspace_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify user has access to workspace
            try:
                workspace = request.user.mapping_user_workspaces.get(id=workspace_id)
            except Workspace.DoesNotExist:
                return Response(
                    {'error': 'Workspace not found or access denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            from core.services.meta_integration import MetaIntegrationService
            meta_service = MetaIntegrationService()
            
            # Get OAuth URL
            oauth_url = meta_service.get_oauth_url(workspace_id)
            
            return Response({
                'oauth_url': oauth_url,
                'workspace_id': workspace_id,
                'instructions': [
                    '1. Redirect user to oauth_url',
                    '2. User authorizes on Meta',
                    '3. Meta redirects to oauth_hook with code',
                    '4. Everything else happens automatically!'
                ]
            })
            
        except Exception as e:
            logger.error(f"Error generating OAuth URL: {str(e)}")
            return Response(
                {'error': f'Failed to generate OAuth URL: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MetaWebhookView(viewsets.ViewSet):
    """Separate ViewSet for Meta webhook endpoints only"""
    permission_classes = [AllowAny]  # Webhooks don't use regular auth
    
    @extend_schema(
        summary="🔗 Meta OAuth callback",
        description="""
        Handle OAuth callback from Meta after user authorization.
        
        **Process Flow**:
        1. Exchange authorization code for access token
        2. Fetch user's business accounts and pages
        3. Create or update MetaIntegration record
        4. Set up webhook subscriptions
        
        **🔒 Security**: This endpoint validates the state parameter for CSRF protection.
        **📥 Method**: POST request with parameters from Meta.
        """,
        request={'type': 'object', 'properties': {
            'code': {'type': 'string', 'description': 'Authorization code from Meta'},
            'state': {'type': 'string', 'description': 'State parameter (workspace_id)'}
        }},
        responses={
            200: OpenApiResponse(
                description="✅ OAuth callback processed successfully"
            ),
            400: OpenApiResponse(description="❌ Invalid OAuth parameters"),
            403: OpenApiResponse(description="🚫 Invalid state parameter (CSRF protection)")
        }
    )
    def oauth_hook(self, request):
        """Handle Meta OAuth callback - FULLY AUTOMATED"""
        # Facebook sends GET requests with query parameters
        if request.method == 'GET':
            code = request.query_params.get('code')
            state = request.query_params.get('state')
        else:
            # Fallback for POST requests (legacy)
            code = request.data.get('code')
            state = request.data.get('state')
        
        if not code:
            return Response(
                {'error': 'Authorization code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract workspace_id from state parameter
        workspace_id = state  # For now, we'll use state as workspace_id
        
        try:
            from core.services.meta_integration import MetaIntegrationService
            
            # Get workspace (validate user has access)
            workspace = Workspace.objects.get(id=workspace_id)
            
            logger.info(f"Processing OAuth callback for workspace {workspace_id}")
            
            # Initialize Meta service
            meta_service = MetaIntegrationService()
            
            # STEP 1: Exchange code for access token
            token_data = meta_service.exchange_code_for_token(code)
            
            # STEP 2: Get long-lived token
            long_lived_token_data = meta_service.get_long_lived_token(token_data['access_token'])
            
            # STEP 3: Create integration (this auto-generates verification token and sets up webhook)
            integration = meta_service.create_integration(workspace, long_lived_token_data)
            
            logger.info(f"Successfully created Meta integration {integration.id}")
            
            # Redirect user back to frontend after successful OAuth
            from django.shortcuts import redirect
            return redirect('https://app.hotcalls.de/dashboard/lead-sources?connected=true')
            
        except Workspace.DoesNotExist:
            return Response(
                {'error': 'Workspace not found or access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"OAuth callback error: {str(e)}")
            return Response(
                {'error': f'Failed to create Meta integration: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="📬 Meta lead webhook",
        description="""
        Receive lead data from Meta webhook when new leads are generated.
        
        **Webhook Flow**:
        1. Verify webhook signature using verification token
        2. Parse lead data from Meta format
        3. Map fields using simple field name matching
        4. Create Lead record with mapped data
        5. Link to MetaLeadForm for tracking
        
        **🔒 Security**: Webhook signature verification is mandatory.
        **⚡ Performance**: Webhook processing is asynchronous for reliability.
        """,
        request=MetaLeadWebhookSerializer,
        responses={
            200: OpenApiResponse(description="✅ Lead webhook processed successfully"),
            400: OpenApiResponse(description="❌ Invalid webhook data"),
            401: OpenApiResponse(description="🚫 Invalid webhook signature")
        },
        auth=None  # Webhook endpoints don't use regular auth
    )
    def lead_in(self, request):
        """Handle Meta lead webhook - POST only for actual leads"""
        return self._handle_webhook_data(request)
    
    @extend_schema(
        summary="🔍 Meta webhook verification",
        description="Verify webhook endpoint for Meta (called during setup)",
        responses={200: {'type': 'string'}},
        auth=None
    )
    def verify_webhook(self, request):
        """Handle Meta webhook verification - GET only"""
        return self._handle_webhook_verification(request)
    
    def _handle_webhook_verification(self, request):
        """Handle Meta webhook verification challenge"""
        hub_mode = request.GET.get('hub.mode')
        hub_verify_token = request.GET.get('hub.verify_token')
        hub_challenge = request.GET.get('hub.challenge')
        
        # Validate all required parameters are present
        if not all([hub_mode, hub_verify_token, hub_challenge]):
            logger.warning("Missing required webhook verification parameters")
            return Response('Missing parameters', status=status.HTTP_400_BAD_REQUEST)
        
        # Check if mode is subscribe
        if hub_mode != 'subscribe':
            logger.warning(f"Invalid hub mode: {hub_mode}")
            return Response('Invalid mode', status=status.HTTP_400_BAD_REQUEST)
        
        # Validate verification token against static configuration
        expected_verify_token = getattr(settings, 'META_WEBHOOK_VERIFY_TOKEN', '')
        if not expected_verify_token:
            logger.error("META_WEBHOOK_VERIFY_TOKEN not configured")
            return Response('Webhook verification not configured', status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if hub_verify_token == expected_verify_token:
            logger.info("Meta webhook verification successful")
            return HttpResponse(hub_challenge, content_type='text/plain')
        else:
            logger.warning(f"Invalid verification token received: {hub_verify_token}")
            return Response('Invalid verification token', status=status.HTTP_403_FORBIDDEN)
    
    def _verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Meta webhook signature using app secret"""
        try:
            app_secret = getattr(settings, 'META_APP_SECRET', '')
            if not app_secret:
                logger.error("META_APP_SECRET not configured")
                return False
            
            # Calculate expected signature
            expected_signature = hmac.new(
                app_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Meta sends signature in format: sha256=<hash>
            expected_signature_formatted = f"sha256={expected_signature}"
            
            # Use constant-time comparison to prevent timing attacks
            return hmac.compare_digest(expected_signature_formatted, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    def _handle_webhook_data(self, request):
        """Process incoming lead webhook data"""
        try:
            # Verify webhook signature for security
            signature = request.META.get('HTTP_X_HUB_SIGNATURE_256')
            if not signature:
                logger.warning("Missing X-Hub-Signature-256 header in webhook request")
                return Response('Missing signature', status=status.HTTP_401_UNAUTHORIZED)
            
            if not self._verify_webhook_signature(request.body, signature):
                logger.warning("Invalid webhook signature")
                return Response('Invalid signature', status=status.HTTP_401_UNAUTHORIZED)
            
            serializer = MetaLeadWebhookSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            webhook_data = serializer.validated_data
            processed_leads = []
            
            # Process each entry in the webhook
            for entry in webhook_data['entry']:
                if 'changes' in entry:
                    for change in entry['changes']:
                        if change.get('field') == 'leadgen':
                            lead_data = change.get('value', {})
                            processed_lead = self._process_lead_data(lead_data)
                            if processed_lead:
                                processed_leads.append(processed_lead)
            
            logger.info(f"Processed {len(processed_leads)} leads from webhook")
            
            return Response({
                'message': 'Webhook processed successfully',
                'processed_leads': len(processed_leads),
                'leads': processed_leads
            })
            
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return Response(
                {'error': 'Failed to process webhook'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_lead_data(self, lead_data):
        """Process individual lead data from webhook"""
        try:
            leadgen_id = lead_data.get('leadgen_id')
            page_id = lead_data.get('page_id')
            form_id = lead_data.get('form_id')
            
            if not all([leadgen_id, page_id, form_id]):
                logger.warning("Missing required lead data fields")
                return None
            
            # Find the corresponding Meta integration and lead form
            try:
                meta_integration = MetaIntegration.objects.get(
                    page_id=page_id,
                    status='active'
                )
                meta_lead_form, created = MetaLeadForm.objects.get_or_create(
                    meta_integration=meta_integration,
                    meta_form_id=form_id,
                    defaults={'is_active': False}  # Default to inactive
                )
            except MetaIntegration.DoesNotExist:
                logger.warning(f"No active Meta integration found for page {page_id}")
                return None
            
            # ✅ CHECK: Is this lead form active?
            if not meta_lead_form.is_active:
                logger.info(f"Ignoring lead from inactive form {form_id} (integration: {meta_integration.id})")
                return {
                    'lead_id': None,
                    'meta_leadgen_id': leadgen_id,
                    'form_id': form_id,
                    'workspace': str(meta_integration.workspace.id),
                    'status': 'ignored_inactive_form'
                }
            
            # Use MetaIntegrationService to fetch real lead data and create lead
            meta_service = MetaIntegrationService()
            
            # Process lead with real Facebook API data
            lead = meta_service.process_lead_webhook(lead_data, meta_integration)
            
            if lead:
                return {
                    'lead_id': str(lead.id),
                    'meta_leadgen_id': leadgen_id,
                    'form_id': form_id,
                    'workspace': str(meta_integration.workspace.id)
                }
            else:
                logger.warning(f"Failed to process lead {leadgen_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error processing lead data: {str(e)}")
            return None


@extend_schema_view(
    list=extend_schema(
        summary="📋 List Meta lead forms",
        description="Retrieve Meta lead forms for your workspaces"
    ),
    create=extend_schema(
        summary="📋 Create Meta lead form configuration",
        description="Create configuration for a Meta lead form"
    ),
)
class MetaLeadFormViewSet(viewsets.ModelViewSet):
    """ViewSet for Meta lead forms"""
    serializer_class = MetaLeadFormSerializer
    permission_classes = [MetaIntegrationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MetaLeadFormFilter
    search_fields = ['meta_form_id', 'meta_lead_id']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter by user's workspaces"""
        if self.request.user.is_staff or self.request.user.is_superuser:
            return MetaLeadForm.objects.all()
        
        user_workspaces = self.request.user.mapping_user_workspaces.all()
        return MetaLeadForm.objects.filter(
            meta_integration__workspace__in=user_workspaces
        )
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return MetaLeadFormCreateSerializer
        elif self.action == 'update_selections':
            return MetaLeadFormBulkUpdateSerializer
        return MetaLeadFormSerializer
    
    @extend_schema(
        summary="💾 Update form selections",
        description="""
        Bulk update the active status of multiple Meta lead forms.
        
        **🔐 Permission Requirements**:
        - User must be authenticated and email verified
        - Only forms from user's workspaces can be updated
        
        **📝 Request Format**:
        - Provide a list of form_id to is_active mappings
        - Only specified forms will be updated
        - Unspecified forms remain unchanged
        
        **🎯 Use Cases**:
        - Enable/disable specific lead forms
        - Bulk configuration of form processing
        - Lead source management
        """,
        request=MetaLeadFormBulkUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description="✅ Form selections updated successfully"
            ),
            400: OpenApiResponse(description="❌ Validation error"),
            403: OpenApiResponse(description="🚫 Permission denied"),
        },
        tags=["Meta Integration"]
    )
    @action(detail=False, methods=['post'])
    def update_selections(self, request):
        """Update the active status of multiple lead forms"""
        serializer = MetaLeadFormBulkUpdateSerializer(data=request.data)
        if serializer.is_valid():
            form_selections = serializer.validated_data['form_selections']
            updated_forms = []
            errors = []
            
            # Get user's accessible workspaces
            if request.user.is_staff or request.user.is_superuser:
                user_workspaces = None  # Access to all
            else:
                user_workspaces = request.user.mapping_user_workspaces.all()
            
            # Process each form selection
            for selection in form_selections:
                for form_id, is_active in selection.items():
                    try:
                        # Build queryset with workspace filtering
                        queryset = MetaLeadForm.objects.filter(meta_form_id=form_id)
                        if user_workspaces is not None:
                            queryset = queryset.filter(meta_integration__workspace__in=user_workspaces)
                        
                        # Update the form(s)
                        updated_count = queryset.update(is_active=is_active)
                        
                        if updated_count > 0:
                            updated_forms.append({
                                'form_id': form_id,
                                'is_active': is_active,
                                'updated_count': updated_count
                            })
                            logger.info(f"Updated {updated_count} forms with ID {form_id} to is_active={is_active}")
                        else:
                            errors.append({
                                'form_id': form_id,
                                'error': 'Form not found or access denied'
                            })
                            
                    except Exception as e:
                        logger.error(f"Error updating form {form_id}: {str(e)}")
                        errors.append({
                            'form_id': form_id,
                            'error': str(e)
                        })
            
            return Response({
                'message': f'Updated {len(updated_forms)} form selections',
                'updated_forms': updated_forms,
                'errors': errors,
                'total_updated': len(updated_forms),
                'total_errors': len(errors)
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 