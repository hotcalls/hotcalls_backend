"""Google Calendar API views for OAuth and calendar management"""
import logging
import secrets
from django.utils import timezone
from django.shortcuts import redirect
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from core.models import Calendar, GoogleCalendar, GoogleSubAccount, Workspace
from core.services.google_calendar import GoogleCalendarService
from .serializers import (
    GoogleCalendarSerializer,
    GoogleAuthUrlResponseSerializer,
    GoogleOAuthCallbackSerializer,
    GoogleSubAccountSerializer,
)
from .permissions import GoogleCalendarPermission

logger = logging.getLogger(__name__)


class GoogleCalendarAuthViewSet(viewsets.ViewSet):
    """ViewSet for Google Calendar OAuth authentication"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="🔗 Generate Google OAuth Authorization URL",
        description="""
        Generate Google OAuth authorization URL to start the OAuth flow.
        
        **Process Flow:**
        1. Frontend calls this endpoint
        2. Backend generates Google OAuth URL with required scopes
        3. Frontend redirects user to the returned URL
        4. User authorizes on Google
        5. Google redirects back to callback endpoint
        """,
        request=None,
        responses={
            200: OpenApiResponse(
                response=GoogleAuthUrlResponseSerializer,
                description="✅ Authorization URL generated successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            500: OpenApiResponse(description="💥 Server error generating URL")
        },
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='authorize')
    def authorize(self, request):
        """Generate Google OAuth authorization URL"""
        try:
            # Generate state for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Store user ID in session for callback
            request.session[f'google_oauth_state_{state}'] = {
                'user_id': str(request.user.id),
                'workspace_id': request.data.get('workspace_id'),
                'created_at': timezone.now().isoformat()
            }
            
            # Generate authorization URL
            authorization_url = GoogleCalendarService.get_authorization_url(state=state)
            
            logger.info(f"Generated Google OAuth URL for user {request.user.email}")
            
            return Response({
                'authorization_url': authorization_url,
                'state': state,
                'message': 'Redirect user to authorization URL'
            })
            
        except Exception as e:
            logger.error(f"Failed to generate Google OAuth URL: {str(e)}")
            return Response({
                'error': 'Failed to generate authorization URL',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🔗 Google OAuth Callback",
        description="""
        Handle Google OAuth callback and create calendar connection.
        
        **Process Flow:**
        1. Receives authorization code from Google
        2. Exchanges code for access & refresh tokens
        3. Creates GoogleCalendar entry with tokens
        4. Syncs user's calendars from Google
        5. Returns success with calendar list
        """,
        responses={
            200: OpenApiResponse(
                response=GoogleOAuthCallbackSerializer,
                description="✅ OAuth successful, calendars synced"
            ),
            400: OpenApiResponse(description="❌ OAuth failed or missing code"),
            401: OpenApiResponse(description="🚫 Invalid state parameter"),
            500: OpenApiResponse(description="💥 Server error during OAuth")
        },
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['get'], url_path='callback', permission_classes=[AllowAny])
    def callback(self, request):
        """Handle Google OAuth callback"""
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        if error:
            logger.warning(f"Google OAuth error: {error}")
            return Response({'error': f'OAuth failed: {error}'}, status=status.HTTP_400_BAD_REQUEST)
            
        if not code:
            return Response({'error': 'Missing authorization code'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate state
        session_key = f'google_oauth_state_{state}'
        state_data = request.session.get(session_key)
        
        if not state_data:
            logger.warning(f"Invalid or expired state: {state}")
            return Response({'error': 'Invalid or expired state'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Get user and workspace from state
            from core.models import User
            user = User.objects.get(id=state_data['user_id'])
            workspace_id = state_data.get('workspace_id')
            
            if workspace_id:
                workspace = Workspace.objects.get(id=workspace_id, users=user)
            else:
                # Use user's first workspace
                workspace = user.workspaces.first()
                if not workspace:
                    return Response({'error': 'No workspace found for user'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Exchange code for tokens
            service = GoogleCalendarService()
            tokens = service.exchange_code_for_tokens(code)
            
            # Get user info from Google
            user_info = service.get_user_info(tokens['access_token'])
            
            # Create or update calendar and GoogleCalendar
            calendar, created = Calendar.objects.update_or_create(
                workspace=workspace,
                name=f"{user_info['email']} - Google Calendar",
                provider='google',
                defaults={'active': True}
            )
            
            # Create or update GoogleCalendar with OAuth tokens
            google_calendar, gc_created = GoogleCalendar.objects.update_or_create(
                calendar=calendar,
                defaults={
                    'user': user,
                    'account_email': user_info['email'],
                    'refresh_token': tokens['refresh_token'],
                    'access_token': tokens['access_token'],
                    'token_expires_at': timezone.now() + timezone.timedelta(seconds=tokens['expires_in']),
                    'scopes': tokens.get('scope', '').split(),
                    'external_id': user_info.get('id', user_info['email']),
                    'time_zone': user_info.get('timezone', 'UTC'),
                    'access_role': 'owner',
                }
            )
            
            # Create self sub-account if it doesn't exist
            GoogleSubAccount.objects.get_or_create(
                google_calendar=google_calendar,
                act_as_email=google_calendar.account_email,
                defaults={
                    'act_as_user_id': user_info.get('id', ''),
                    'relationship': 'self',
                    'active': True
                }
            )
            
            # Discover and create sub-accounts for shared/delegated calendars
            try:
                # Get calendar list from Google
                from googleapiclient.discovery import build
                from google.oauth2.credentials import Credentials
                
                creds = Credentials(
                    token=tokens['access_token'],
                    refresh_token=tokens['refresh_token'],
                    token_uri='https://oauth2.googleapis.com/token',
                    client_id=service.client_id,
                    client_secret=service.client_secret,
                    scopes=tokens.get('scope', '').split()
                )
                
                calendar_service = build('calendar', 'v3', credentials=creds)
                calendar_list = calendar_service.calendarList().list().execute()
                
                for cal_entry in calendar_list.get('items', []):
                    # Skip if this is the primary calendar (already handled as 'self')
                    if cal_entry.get('primary'):
                        continue
                    
                    # Determine relationship type
                    access_role = cal_entry.get('accessRole', 'reader')
                    cal_id = cal_entry.get('id', '')
                    summary = cal_entry.get('summary', '')
                    
                    # Determine relationship based on calendar ID and access role
                    if '@group.calendar.google.com' in cal_id:
                        relationship = 'shared'
                    elif '@resource.calendar.google.com' in cal_id:
                        relationship = 'resource'
                    elif access_role in ['owner', 'writer']:
                        relationship = 'delegate'
                    else:
                        relationship = 'shared'
                    
                    # Create sub-account for this calendar
                    GoogleSubAccount.objects.get_or_create(
                        google_calendar=google_calendar,
                        act_as_email=cal_id,
                        defaults={
                            'act_as_user_id': '',  # Will be populated if needed
                            'relationship': relationship,
                            'active': True
                        }
                    )
                    
                    logger.info(f"Created {relationship} sub-account for calendar: {summary} ({cal_id})")
                    
            except Exception as e:
                logger.warning(f"Could not discover shared calendars: {str(e)}")
                # Continue anyway - at least we have the self account
            
            # Sync calendars from Google
            synced_calendars = service.sync_calendars(google_calendar)
            
            # Clean up session state
            del request.session[session_key]
            
            logger.info(f"Successfully connected Google Calendar for {user.email}")
            
            # Redirect to frontend with success
            frontend_url = "https://app.hotcalls.de/dashboard/calendars?connected=true"
            return redirect(frontend_url)
            
        except Exception as e:
            logger.error(f"Google OAuth callback error: {str(e)}")
            return Response({
                'error': 'Failed to complete OAuth flow',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🔗 Disconnect Google Calendar",
        description="""
        Disconnect Google Calendar and revoke OAuth tokens.
        
        **Process:**
        1. Revokes tokens with Google
        2. Deletes GoogleCalendar entry
        3. Deletes associated Calendar entry
        """,
        request={'type': 'object', 'properties': {'calendar_id': {'type': 'string'}}},
        responses={
            200: OpenApiResponse(description="✅ Calendar disconnected successfully"),
            404: OpenApiResponse(description="❌ Calendar not found"),
            500: OpenApiResponse(description="💥 Error disconnecting calendar")
        },
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='disconnect')
    def disconnect(self, request):
        """Disconnect Google Calendar"""
        calendar_id = request.data.get('calendar_id')
        
        if not calendar_id:
            return Response({'error': 'calendar_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the calendar
            calendar = Calendar.objects.get(
                id=calendar_id,
                workspace__users=request.user,
                provider='google'
            )
            
            # Get GoogleCalendar
            google_calendar = GoogleCalendar.objects.get(calendar=calendar)
            
            # Revoke tokens with Google
            service = GoogleCalendarService()
            service.revoke_tokens(google_calendar)
            
            # Delete GoogleCalendar and Calendar
            google_calendar.delete()
            calendar.delete()
            
            logger.info(f"Disconnected Google Calendar {calendar_id} for user {request.user.email}")
            
            return Response({
                'success': True,
                'message': 'Google Calendar disconnected successfully'
            })
            
        except Calendar.DoesNotExist:
            return Response({'error': 'Calendar not found'}, status=status.HTTP_404_NOT_FOUND)
        except GoogleCalendar.DoesNotExist:
            # Calendar exists but no GoogleCalendar - just delete the calendar
            calendar.delete()
            return Response({'success': True, 'message': 'Calendar removed'})
        except Exception as e:
            logger.error(f"Error disconnecting Google Calendar: {str(e)}")
            return Response({
                'error': 'Failed to disconnect calendar',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema_view(
    list=extend_schema(
        summary="📅 List Google Calendars",
        description="Retrieve all Google calendars in your workspaces",
        tags=["Google Calendar"]
    ),
    retrieve=extend_schema(
        summary="📄 Get Google Calendar details",
        description="Get details of a specific Google calendar",
        tags=["Google Calendar"]
    )
)
class GoogleCalendarViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Google Calendar management"""
    serializer_class = GoogleCalendarSerializer
    permission_classes = [GoogleCalendarPermission]
    
    def get_queryset(self):
        """Get Google calendars for user's workspaces"""
        user = self.request.user
        if user.is_superuser:
            return GoogleCalendar.objects.all().select_related('calendar__workspace', 'user')
        
        return GoogleCalendar.objects.filter(
            calendar__workspace__users=user
        ).select_related('calendar__workspace', 'user')
    

    
    @extend_schema(
        summary="🔄 Sync Google Calendars",
        description="""
        Force sync calendars from Google for a specific connection.
        
        **Process:**
        1. Fetches latest calendar list from Google
        2. Updates calendar metadata
        3. Returns updated calendar list
        """,
        request={'type': 'object', 'properties': {'google_calendar_id': {'type': 'string'}}},
        responses={
            200: OpenApiResponse(description="✅ Calendars synced successfully"),
            404: OpenApiResponse(description="❌ Google calendar not found"),
            500: OpenApiResponse(description="💥 Sync failed")
        },
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='sync')
    def sync(self, request):
        """Force sync calendars from Google"""
        google_calendar_id = request.data.get('google_calendar_id')
        
        if not google_calendar_id:
            return Response({'error': 'google_calendar_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the Google calendar
            google_calendar = GoogleCalendar.objects.get(
                id=google_calendar_id,
                calendar__workspace__users=request.user
            )
            
            # Sync calendars
            service = GoogleCalendarService()
            synced_calendars = service.sync_calendars(google_calendar)
            
            # Update last sync time
            google_calendar.last_sync = timezone.now()
            google_calendar.sync_errors = {}
            google_calendar.save()
            
            return Response({
                'success': True,
                'message': f'Synced {len(synced_calendars)} calendars',
                'calendars': GoogleCalendarSerializer(synced_calendars, many=True).data
            })
            
        except GoogleCalendar.DoesNotExist:
            return Response({'error': 'Google calendar not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Calendar sync failed: {str(e)}")
            
            # Update sync errors
            if 'google_calendar' in locals():
                google_calendar.sync_errors = {'error': str(e), 'timestamp': timezone.now().isoformat()}
                google_calendar.save()
            
            return Response({
                'error': 'Sync failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🗑️ Delete Google Calendar",
        description="Delete a specific Google calendar connection",
        responses={
            204: OpenApiResponse(description="✅ Calendar deleted successfully"),
            404: OpenApiResponse(description="❌ Calendar not found")
        },
        tags=["Google Calendar"]
    )
    def destroy(self, request, *args, **kwargs):
        """Delete Google calendar"""
        instance = self.get_object()
        
        # Delete the associated Calendar as well
        calendar = instance.calendar
        instance.delete()
        calendar.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="📋 List Google Sub-Accounts",
        description="List all sub-accounts (shared/delegated calendars) for Google Calendar connections",
        tags=["Google Calendar"]
    ),
    create=extend_schema(
        summary="➕ Create Google Sub-Account",
        description="Add a new sub-account (shared/delegated calendar) to a Google Calendar connection",
        tags=["Google Calendar"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get Google Sub-Account",
        description="Retrieve details of a specific Google sub-account",
        tags=["Google Calendar"]
    ),
    update=extend_schema(
        summary="✏️ Update Google Sub-Account",
        description="Update a Google sub-account configuration",
        tags=["Google Calendar"]
    ),
    partial_update=extend_schema(
        summary="📝 Partially Update Google Sub-Account",
        description="Partially update a Google sub-account configuration",
        tags=["Google Calendar"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete Google Sub-Account",
        description="Remove a Google sub-account (shared/delegated calendar)",
        tags=["Google Calendar"]
    )
)
class GoogleSubAccountViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Google sub-accounts (shared/delegated calendars).
    
    Sub-accounts represent different Google identities that the main account can act as:
    - **self**: The main account itself
    - **shared**: Shared calendar from another user
    - **delegate**: Delegated access to another user's calendar
    - **domain_impersonation**: Domain-wide delegation (service account)
    - **resource**: Resource calendar (room, equipment)
    """
    serializer_class = GoogleSubAccountSerializer
    permission_classes = [IsAuthenticated, GoogleCalendarPermission]
    
    def get_queryset(self):
        """Filter sub-accounts by user's workspaces"""
        return GoogleSubAccount.objects.filter(
            google_calendar__calendar__workspace__users=self.request.user
        ).select_related(
            'google_calendar',
            'google_calendar__calendar',
            'google_calendar__calendar__workspace'
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Validate that user has access to the Google calendar"""
        google_calendar = serializer.validated_data.get('google_calendar')
        
        # Check user has access to this Google calendar
        if not google_calendar.calendar.workspace.users.filter(id=self.request.user.id).exists():
            raise serializers.ValidationError("You don't have access to this Google calendar")
        
        # Check for duplicate sub-accounts
        existing = GoogleSubAccount.objects.filter(
            google_calendar=google_calendar,
            act_as_email=serializer.validated_data.get('act_as_email')
        ).first()
        
        if existing:
            raise serializers.ValidationError(
                f"Sub-account for {serializer.validated_data.get('act_as_email')} already exists"
            )
        
        serializer.save()
    
    @action(detail=False, methods=['get'], url_path='by-calendar/(?P<google_calendar_id>[^/.]+)')
    def by_calendar(self, request, google_calendar_id=None):
        """Get all sub-accounts for a specific Google calendar"""
        sub_accounts = self.get_queryset().filter(google_calendar_id=google_calendar_id)
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
