"""Outlook Calendar API views for OAuth and calendar management"""
import logging
import secrets
import hashlib
import base64
from django.utils import timezone
from django.shortcuts import redirect
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from core.models import Calendar, OutlookCalendar, OutlookSubAccount, Workspace
from core.services.outlook_calendar import OutlookCalendarService
from .serializers import (
    OutlookCalendarSerializer,
    OutlookAuthUrlResponseSerializer,
    OutlookOAuthCallbackSerializer,
    OutlookSubAccountSerializer,
)
from .permissions import OutlookCalendarPermission

logger = logging.getLogger(__name__)


class OutlookCalendarAuthViewSet(viewsets.ViewSet):
    """ViewSet for Outlook Calendar OAuth authentication"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="🔗 Generate Outlook OAuth Authorization URL",
        description="""
        Generate Microsoft OAuth authorization URL to start the OAuth flow.
        
        **Process Flow:**
        1. Frontend calls this endpoint
        2. Backend generates Microsoft OAuth URL with required scopes
        3. Frontend redirects user to the returned URL
        4. User authorizes on Microsoft
        5. Microsoft redirects back to callback endpoint
        """,
        request=None,
        responses={
            200: OpenApiResponse(
                response=OutlookAuthUrlResponseSerializer,
                description="✅ Authorization URL generated successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            500: OpenApiResponse(description="💥 Server error generating URL")
        },
        tags=["Outlook Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='authorize')
    def authorize(self, request):
        """Generate Microsoft OAuth authorization URL"""
        try:
            # Get workspace from request
            workspace_id = request.data.get('workspace_id')
            if not workspace_id:
                return Response(
                    {'error': 'workspace_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify user has access to workspace
            try:
                workspace = Workspace.objects.get(
                    id=workspace_id,
                    users=request.user
                )
            except Workspace.DoesNotExist:
                return Response(
                    {'error': 'Workspace not found or access denied'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Generate state for CSRF protection
            state_data = {
                'user_id': str(request.user.id),
                'workspace_id': str(workspace.id),
                'timestamp': timezone.now().isoformat(),
                'nonce': secrets.token_urlsafe(16)
            }
            
            # Create state string
            import json
            state_json = json.dumps(state_data)
            state_bytes = state_json.encode('utf-8')
            state = base64.urlsafe_b64encode(state_bytes).decode('utf-8')
            
            # Generate authorization URL
            service = OutlookCalendarService()
            auth_url = service.get_authorization_url(state)
            
            return Response({
                'authorization_url': auth_url,
                'state': state,
                'message': 'Redirect user to authorization_url to complete OAuth flow'
            })
            
        except Exception as e:
            logger.error(f"Error generating Outlook auth URL: {str(e)}")
            return Response(
                {'error': 'Failed to generate authorization URL', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        summary="🔒 Handle Outlook OAuth Callback",
        description="""
        Handle the OAuth callback from Microsoft after user authorization.
        This endpoint processes the authorization code and exchanges it for tokens.
        """,
        request=None,
        responses={
            200: OpenApiResponse(
                response=OutlookOAuthCallbackSerializer,
                description="✅ OAuth callback processed successfully"
            ),
            400: OpenApiResponse(description="❌ Invalid callback parameters"),
            500: OpenApiResponse(description="💥 Token exchange failed")
        },
        tags=["Outlook Calendar"]
    )
    @action(detail=False, methods=['get'], url_path='callback', permission_classes=[AllowAny])
    def callback(self, request):
        """Handle OAuth callback from Microsoft"""
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        # Handle OAuth errors
        if error:
            error_description = request.GET.get('error_description', 'Unknown error')
            logger.error(f"Outlook OAuth error: {error} - {error_description}")
            return redirect(f"/calendar?error={error}&description={error_description}")
        
        if not code or not state:
            return redirect("/calendar?error=missing_parameters")
        
        try:
            # Decode and validate state
            import json
            state_bytes = base64.urlsafe_b64decode(state.encode('utf-8'))
            state_json = state_bytes.decode('utf-8')
            state_data = json.loads(state_json)
            
            user_id = state_data.get('user_id')
            workspace_id = state_data.get('workspace_id')
            
            if not user_id or not workspace_id:
                return redirect("/calendar?error=invalid_state")
            
            # Get workspace
            workspace = Workspace.objects.get(id=workspace_id)
            
            # Exchange code for tokens
            service = OutlookCalendarService()
            tokens = service.exchange_code_for_tokens(code)
            
            if not tokens:
                return redirect("/calendar?error=token_exchange_failed")
            
            # Get user info from tokens
            user_info = service.get_user_info(tokens['access_token'])
            
            # Create or update OutlookCalendar
            calendar_name = f"{user_info.get('displayName', 'Outlook')} Calendar"
            
            # Create generic Calendar first
            calendar, created = Calendar.objects.get_or_create(
                workspace=workspace,
                name=calendar_name,
                provider='outlook',
                defaults={'active': True}
            )
            
            # Create or update OutlookCalendar
            outlook_calendar, created = OutlookCalendar.objects.update_or_create(
                calendar=calendar,
                defaults={
                    'user_id': user_id,
                    'primary_email': user_info.get('mail') or user_info.get('userPrincipalName'),
                    'tenant_id': tokens.get('tid', ''),
                    'ms_user_id': user_info.get('id', ''),
                    'display_name': user_info.get('displayName', ''),
                    'timezone_windows': user_info.get('mailboxSettings', {}).get('timeZone', ''),
                    'refresh_token': tokens['refresh_token'],
                    'access_token': tokens['access_token'],
                    'token_expires_at': timezone.now() + timezone.timedelta(seconds=tokens.get('expires_in', 3600)),
                    'scopes_granted': tokens.get('scope', '').split(' '),
                    'external_id': user_info.get('id', ''),
                    'can_edit': True
                }
            )
            
            # Create self sub-account if it doesn't exist
            from core.models import OutlookSubAccount
            OutlookSubAccount.objects.get_or_create(
                outlook_calendar=outlook_calendar,
                act_as_upn=outlook_calendar.primary_email,
                defaults={
                    'mailbox_object_id': outlook_calendar.ms_user_id,
                    'relationship': 'self',
                    'active': True
                }
            )
            
            # Discover and create sub-accounts for shared/delegated mailboxes
            try:
                import requests
                
                # Get shared mailboxes the user has access to
                headers = {'Authorization': f'Bearer {tokens["access_token"]}'}
                
                # Try to get shared mailboxes (requires specific permissions)
                shared_mailboxes_url = 'https://graph.microsoft.com/v1.0/me/mailboxSettings/sharedMailboxes'
                try:
                    shared_response = requests.get(shared_mailboxes_url, headers=headers)
                    if shared_response.status_code == 200:
                        shared_data = shared_response.json()
                        for mailbox in shared_data.get('value', []):
                            OutlookSubAccount.objects.get_or_create(
                                outlook_calendar=outlook_calendar,
                                act_as_upn=mailbox.get('emailAddress', ''),
                                defaults={
                                    'mailbox_object_id': mailbox.get('id', ''),
                                    'relationship': 'shared',
                                    'active': True
                                }
                            )
                            logger.info(f"Created shared sub-account for mailbox: {mailbox.get('emailAddress')}")
                except Exception as e:
                    logger.debug(f"Could not get shared mailboxes (may need additional permissions): {e}")
                
                # Get calendars the user has access to
                calendars_url = 'https://graph.microsoft.com/v1.0/me/calendars'
                calendars_response = requests.get(calendars_url, headers=headers)
                
                if calendars_response.status_code == 200:
                    calendars_data = calendars_response.json()
                    for calendar in calendars_data.get('value', []):
                        # Skip the default calendar (already handled as 'self')
                        if calendar.get('isDefaultCalendar'):
                            continue
                        
                        owner_email = calendar.get('owner', {}).get('address')
                        if owner_email and owner_email != outlook_calendar.primary_email:
                            # This is a delegated calendar
                            OutlookSubAccount.objects.get_or_create(
                                outlook_calendar=outlook_calendar,
                                act_as_upn=owner_email,
                                defaults={
                                    'mailbox_object_id': '',
                                    'relationship': 'delegate',
                                    'active': True
                                }
                            )
                            logger.info(f"Created delegate sub-account for calendar: {calendar.get('name')} ({owner_email})")
                
                # Try to get room/resource calendars (if user has permissions)
                rooms_url = 'https://graph.microsoft.com/v1.0/places/microsoft.graph.room'
                try:
                    rooms_response = requests.get(rooms_url, headers=headers)
                    if rooms_response.status_code == 200:
                        rooms_data = rooms_response.json()
                        for room in rooms_data.get('value', []):
                            OutlookSubAccount.objects.get_or_create(
                                outlook_calendar=outlook_calendar,
                                act_as_upn=room.get('emailAddress', ''),
                                defaults={
                                    'mailbox_object_id': room.get('id', ''),
                                    'relationship': 'resource',
                                    'active': True
                                }
                            )
                            logger.info(f"Created resource sub-account for room: {room.get('displayName')}")
                except Exception as e:
                    logger.debug(f"Could not get room resources (may need additional permissions): {e}")
                    
            except Exception as e:
                logger.warning(f"Could not discover shared/delegated calendars: {str(e)}")
                # Continue anyway - at least we have the self account
            
            # Redirect to frontend with success
            return redirect(f"/calendar?outlook_connected=true&calendar_id={calendar.id}")
            
        except Exception as e:
            logger.error(f"Outlook OAuth callback error: {str(e)}")
            return redirect(f"/calendar?error=callback_failed&details={str(e)}")


@extend_schema_view(
    list=extend_schema(
        summary="📋 List Outlook Calendars",
        description="List all Outlook calendar connections for the user's workspaces",
        tags=["Outlook Calendar"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get Outlook Calendar",
        description="Retrieve details of a specific Outlook calendar connection",
        tags=["Outlook Calendar"]
    ),
    update=extend_schema(
        summary="✏️ Update Outlook Calendar",
        description="Update an Outlook calendar connection",
        tags=["Outlook Calendar"]
    ),
    partial_update=extend_schema(
        summary="📝 Partially Update Outlook Calendar",
        description="Partially update an Outlook calendar connection",
        tags=["Outlook Calendar"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete Outlook Calendar",
        description="Delete an Outlook calendar connection and revoke access",
        tags=["Outlook Calendar"]
    )
)
class OutlookCalendarViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Outlook calendar connections.
    
    This viewset handles CRUD operations for Outlook calendars that have been
    connected via OAuth. It does not handle the OAuth flow itself - that's
    handled by OutlookCalendarAuthViewSet.
    """
    serializer_class = OutlookCalendarSerializer
    permission_classes = [IsAuthenticated, OutlookCalendarPermission]
    
    def get_queryset(self):
        """Filter calendars by user's workspaces"""
        return OutlookCalendar.objects.filter(
            calendar__workspace__users=self.request.user
        ).select_related('calendar', 'calendar__workspace')
    
    @extend_schema(
        summary="🔄 Sync Outlook Calendars",
        description="""
        Force sync calendars from Outlook.
        This will fetch the latest calendar data from Microsoft Graph API.
        """,
        request=None,
        responses={
            200: OpenApiResponse(
                response=OutlookCalendarSerializer,
                description="✅ Sync completed successfully"
            ),
            400: OpenApiResponse(description="❌ Invalid request"),
            404: OpenApiResponse(description="❌ Outlook calendar not found"),
            500: OpenApiResponse(description="💥 Sync failed")
        },
        tags=["Outlook Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='sync')
    def sync(self, request):
        """Force sync calendars from Outlook"""
        outlook_calendar_id = request.data.get('outlook_calendar_id')
        
        if not outlook_calendar_id:
            return Response({'error': 'outlook_calendar_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the Outlook calendar
            outlook_calendar = OutlookCalendar.objects.get(
                id=outlook_calendar_id,
                calendar__workspace__users=request.user
            )
            
            # Sync calendars
            service = OutlookCalendarService()
            synced_calendars = service.sync_calendars(outlook_calendar)
            
            # Update last sync time
            outlook_calendar.last_sync = timezone.now()
            outlook_calendar.sync_errors = {}
            outlook_calendar.save()
            
            return Response({
                'success': True,
                'message': f'Synced {len(synced_calendars)} calendars',
                'calendars': OutlookCalendarSerializer(synced_calendars, many=True).data
            })
            
        except OutlookCalendar.DoesNotExist:
            return Response({'error': 'Outlook calendar not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Calendar sync failed: {str(e)}")
            
            # Update sync errors
            if 'outlook_calendar' in locals():
                outlook_calendar.sync_errors = {'error': str(e), 'timestamp': timezone.now().isoformat()}
                outlook_calendar.save()
            
            return Response({
                'error': 'Sync failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🗑️ Delete Outlook Calendar",
        description="Delete a specific Outlook calendar connection",
        responses={
            204: OpenApiResponse(description="✅ Calendar deleted successfully"),
            404: OpenApiResponse(description="❌ Calendar not found")
        },
        tags=["Outlook Calendar"]
    )
    def destroy(self, request, *args, **kwargs):
        """Delete Outlook calendar"""
        instance = self.get_object()
        
        # Delete the associated Calendar as well
        calendar = instance.calendar
        instance.delete()
        calendar.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="📋 List Outlook Sub-Accounts",
        description="List all sub-accounts (shared/delegated mailboxes) for Outlook Calendar connections",
        tags=["Outlook Calendar"]
    ),
    create=extend_schema(
        summary="➕ Create Outlook Sub-Account",
        description="Add a new sub-account (shared/delegated mailbox) to an Outlook Calendar connection",
        tags=["Outlook Calendar"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get Outlook Sub-Account",
        description="Retrieve details of a specific Outlook sub-account",
        tags=["Outlook Calendar"]
    ),
    update=extend_schema(
        summary="✏️ Update Outlook Sub-Account",
        description="Update an Outlook sub-account configuration",
        tags=["Outlook Calendar"]
    ),
    partial_update=extend_schema(
        summary="📝 Partially Update Outlook Sub-Account",
        description="Partially update an Outlook sub-account configuration",
        tags=["Outlook Calendar"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete Outlook Sub-Account",
        description="Remove an Outlook sub-account (shared/delegated mailbox)",
        tags=["Outlook Calendar"]
    )
)
class OutlookSubAccountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Outlook sub-accounts (shared/delegated mailboxes).
    
    Sub-accounts represent different Microsoft identities that the main account can act as:
    - **self**: The main account itself
    - **shared**: Shared mailbox/calendar
    - **delegate**: Delegated access to another user's calendar
    - **app_only**: Application-permission impersonation
    - **resource**: Room/equipment calendar
    """
    serializer_class = OutlookSubAccountSerializer
    permission_classes = [IsAuthenticated, OutlookCalendarPermission]
    
    def get_queryset(self):
        """Filter sub-accounts by user's workspaces"""
        return OutlookSubAccount.objects.filter(
            outlook_calendar__calendar__workspace__users=self.request.user
        ).select_related(
            'outlook_calendar',
            'outlook_calendar__calendar',
            'outlook_calendar__calendar__workspace'
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Validate that user has access to the Outlook calendar"""
        outlook_calendar = serializer.validated_data.get('outlook_calendar')
        
        # Check user has access to this Outlook calendar
        if not outlook_calendar.calendar.workspace.users.filter(id=self.request.user.id).exists():
            raise serializers.ValidationError("You don't have access to this Outlook calendar")
        
        # Check for duplicate sub-accounts
        existing = OutlookSubAccount.objects.filter(
            outlook_calendar=outlook_calendar,
            act_as_upn=serializer.validated_data.get('act_as_upn')
        ).first()
        
        if existing:
            raise serializers.ValidationError(
                f"Sub-account for {serializer.validated_data.get('act_as_upn')} already exists"
            )
        
        serializer.save()
    
    @action(detail=False, methods=['get'], url_path='by-calendar/(?P<outlook_calendar_id>[^/.]+)')
    def by_calendar(self, request, outlook_calendar_id=None):
        """Get all sub-accounts for a specific Outlook calendar"""
        sub_accounts = self.get_queryset().filter(outlook_calendar_id=outlook_calendar_id)
        serializer = self.get_serializer(sub_accounts, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        """Toggle the active status of a sub-account"""
        sub_account = self.get_object()
        sub_account.active = not sub_account.active
        sub_account.save()
        
        return Response({
            'success': True,
            'active': sub_account.active,
            'message': f"Sub-account {'activated' if sub_account.active else 'deactivated'}"
        })