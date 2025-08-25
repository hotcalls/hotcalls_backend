"""Outlook Calendar API views for OAuth and calendar management"""
import logging
import secrets
import hashlib
import base64
from django.utils import timezone
from django.shortcuts import redirect
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from core.models import Calendar, OutlookCalendar, Workspace
from core.services.outlook_calendar import OutlookCalendarService
from .serializers import (
    OutlookCalendarSerializer,
    OutlookAuthUrlResponseSerializer,
    OutlookOAuthCallbackSerializer,
)
from .permissions import OutlookCalendarPermission

logger = logging.getLogger(__name__)


class OutlookCalendarAuthViewSet(viewsets.ViewSet):
    """ViewSet for Outlook Calendar OAuth authentication"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="🔗 Generate Outlook OAuth Authorization URL",
        description="""
        Generate Microsoft OAuth authorization URL with PKCE to start the OAuth flow.
        
        **Process Flow:**
        1. Frontend calls this endpoint
        2. Backend generates OAuth URL with PKCE parameters
        3. Frontend redirects user to the returned URL
        4. User authorizes on Microsoft
        5. Microsoft redirects back to callback endpoint
        """,
        request={'type': 'object', 'properties': {
            'workspace_id': {'type': 'string', 'format': 'uuid', 'required': False},
            'intent': {'type': 'string', 'required': False}
        }},
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
        """Generate Microsoft OAuth authorization URL with PKCE"""
        try:
            # Generate PKCE parameters
            state = secrets.token_urlsafe(32)
            code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('utf-8')
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).rstrip(b'=').decode('utf-8')
            
            # Store state and PKCE verifier in session
            request.session[f'ms_oauth_state_{state}'] = {
                'user_id': str(request.user.id),
                'workspace_id': request.data.get('workspace_id'),
                'code_verifier': code_verifier,
                'intent': request.data.get('intent'),
                'created_at': timezone.now().isoformat()
            }
            
            # Generate authorization URL
            authorization_url = OutlookCalendarService.build_authorize_url(
                state=state,
                code_challenge=code_challenge,
                intent=request.data.get('intent')
            )
            
            logger.info(f"Generated Microsoft OAuth URL for user {request.user.email}")
            
            return Response({
                'authorization_url': authorization_url,
                'state': state,
                'message': 'Redirect user to authorization URL'
            })
            
        except Exception as e:
            logger.error(f"Failed to generate Microsoft OAuth URL: {str(e)}")
            return Response({
                'error': 'Failed to generate authorization URL',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🔗 Outlook OAuth Callback",
        description="""
        Handle Microsoft OAuth callback and create calendar connection.
        
        **Process Flow:**
        1. Receives authorization code from Microsoft
        2. Exchanges code for access & refresh tokens using PKCE
        3. Creates OutlookCalendar entry with tokens
        4. Syncs user's calendars from Microsoft Graph
        5. Returns success with calendar list
        """,
        responses={
            200: OpenApiResponse(
                response=OutlookOAuthCallbackSerializer,
                description="✅ OAuth successful, calendars synced"
            ),
            400: OpenApiResponse(description="❌ OAuth failed or missing code"),
            401: OpenApiResponse(description="🚫 Invalid state parameter"),
            500: OpenApiResponse(description="💥 Server error during OAuth")
        },
        tags=["Outlook Calendar"]
    )
    @action(detail=False, methods=['get'], url_path='callback', permission_classes=[AllowAny])
    def callback(self, request):
        """Handle Microsoft OAuth callback"""
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        error_description = request.GET.get('error_description')
        
        if error:
            logger.warning(f"Microsoft OAuth error: {error} - {error_description}")
            return Response({
                'error': f'OAuth failed: {error}',
                'description': error_description
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if not code:
            return Response({'error': 'Missing authorization code'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate state and get PKCE verifier
        session_key = f'ms_oauth_state_{state}'
        state_data = request.session.get(session_key)
        
        if not state_data:
            logger.warning(f"Invalid or expired state: {state}")
            return Response({'error': 'Invalid or expired state'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Get user and workspace from state
            from core.models import User
            user = User.objects.get(id=state_data['user_id'])
            workspace_id = state_data.get('workspace_id')
            code_verifier = state_data['code_verifier']
            
            if workspace_id:
                workspace = Workspace.objects.get(id=workspace_id, users=user)
            else:
                # Use user's first workspace
                workspace = user.workspaces.first()
                if not workspace:
                    return Response({'error': 'No workspace found for user'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Exchange code for tokens using PKCE
            service = OutlookCalendarService()
            tokens = service.exchange_code_for_tokens(code, code_verifier)
            
            # Get user info from Microsoft Graph
            user_info = service.get_user_info(tokens['access_token'])
            
            # Create or update calendar and OutlookCalendar
            calendar, created = Calendar.objects.update_or_create(
                workspace=workspace,
                name=f"{user_info['mail']} - Outlook Calendar",
                provider='outlook',
                defaults={'active': True}
            )
            
            # Create or update OutlookCalendar with OAuth tokens
            outlook_calendar, oc_created = OutlookCalendar.objects.update_or_create(
                calendar=calendar,
                defaults={
                    'user': user,
                    'primary_email': user_info['mail'],
                    'tenant_id': tokens.get('tid', ''),
                    'ms_user_id': user_info['id'],
                    'display_name': user_info.get('displayName', ''),
                    'timezone_windows': user_info.get('mailboxSettings', {}).get('timeZone', ''),
                    'refresh_token': tokens['refresh_token'],
                    'access_token': tokens['access_token'],
                    'token_expires_at': timezone.now() + timezone.timedelta(seconds=tokens['expires_in']),
                    'scopes_granted': tokens.get('scope', '').split(),
                    'external_id': 'primary',  # Will be updated during sync
                    'can_edit': True,
                }
            )
            
            # Sync calendars from Microsoft
            synced_calendars = service.sync_calendars(outlook_calendar)
            
            # Clean up session state
            del request.session[session_key]
            
            logger.info(f"Successfully connected Outlook Calendar for {user.email}")
            
            # Redirect to frontend with success
            frontend_url = "https://app.hotcalls.de/dashboard/calendars?connected=true&provider=outlook"
            return redirect(frontend_url)
            
        except Exception as e:
            logger.error(f"Microsoft OAuth callback error: {str(e)}")
            return Response({
                'error': 'Failed to complete OAuth flow',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🔗 Disconnect Outlook Calendar",
        description="""
        Disconnect Outlook Calendar and revoke OAuth tokens.
        
        **Process:**
        1. Revokes tokens with Microsoft (if possible)
        2. Deletes OutlookCalendar entry
        3. Deletes associated Calendar entry
        """,
        request={'type': 'object', 'properties': {'calendar_id': {'type': 'string'}}},
        responses={
            200: OpenApiResponse(description="✅ Calendar disconnected successfully"),
            404: OpenApiResponse(description="❌ Calendar not found"),
            500: OpenApiResponse(description="💥 Error disconnecting calendar")
        },
        tags=["Outlook Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='disconnect')
    def disconnect(self, request):
        """Disconnect Outlook Calendar"""
        calendar_id = request.data.get('calendar_id')
        
        if not calendar_id:
            return Response({'error': 'calendar_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the calendar
            calendar = Calendar.objects.get(
                id=calendar_id,
                workspace__users=request.user,
                provider='outlook'
            )
            
            # Get OutlookCalendar
            outlook_calendar = OutlookCalendar.objects.get(calendar=calendar)
            
            # Try to revoke tokens with Microsoft (best effort)
            try:
                service = OutlookCalendarService()
                service.revoke_tokens(outlook_calendar)
            except Exception as e:
                logger.warning(f"Failed to revoke Microsoft tokens: {str(e)}")
            
            # Delete OutlookCalendar and Calendar
            outlook_calendar.delete()
            calendar.delete()
            
            logger.info(f"Disconnected Outlook Calendar {calendar_id} for user {request.user.email}")
            
            return Response({
                'success': True,
                'message': 'Outlook Calendar disconnected successfully'
            })
            
        except Calendar.DoesNotExist:
            return Response({'error': 'Calendar not found'}, status=status.HTTP_404_NOT_FOUND)
        except OutlookCalendar.DoesNotExist:
            # Calendar exists but no OutlookCalendar - just delete the calendar
            calendar.delete()
            return Response({'success': True, 'message': 'Calendar removed'})
        except Exception as e:
            logger.error(f"Error disconnecting Outlook Calendar: {str(e)}")
            return Response({
                'error': 'Failed to disconnect calendar',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema_view(
    list=extend_schema(
        summary="📅 List Outlook Calendars",
        description="Retrieve all Outlook calendars in your workspaces",
        tags=["Outlook Calendar"]
    ),
    retrieve=extend_schema(
        summary="📄 Get Outlook Calendar details",
        description="Get details of a specific Outlook calendar",
        tags=["Outlook Calendar"]
    )
)
class OutlookCalendarViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Outlook Calendar management"""
    serializer_class = OutlookCalendarSerializer
    permission_classes = [OutlookCalendarPermission]
    
    def get_queryset(self):
        """Get Outlook calendars for user's workspaces"""
        user = self.request.user
        if user.is_superuser:
            return OutlookCalendar.objects.all().select_related('calendar__workspace', 'user')
        
        return OutlookCalendar.objects.filter(
            calendar__workspace__users=user
        ).select_related('calendar__workspace', 'user')
    

    
    @extend_schema(
        summary="🔄 Sync Outlook Calendars",
        description="""
        Force sync calendars from Microsoft Graph for a specific connection.
        
        **Process:**
        1. Fetches latest calendar list from Microsoft
        2. Updates calendar metadata
        3. Returns updated calendar list
        """,
        request={'type': 'object', 'properties': {'outlook_calendar_id': {'type': 'string'}}},
        responses={
            200: OpenApiResponse(description="✅ Calendars synced successfully"),
            404: OpenApiResponse(description="❌ Outlook calendar not found"),
            500: OpenApiResponse(description="💥 Sync failed")
        },
        tags=["Outlook Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='sync')
    def sync(self, request):
        """Force sync calendars from Microsoft"""
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
