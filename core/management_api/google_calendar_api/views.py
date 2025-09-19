"""Google Calendar API views for OAuth and calendar management"""
import logging
import secrets
from django.conf import settings
from django.utils import timezone
from django.shortcuts import redirect
from rest_framework import viewsets, status
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
    # GoogleSubAccountSerializer,  # REMOVED - sub-accounts managed automatically
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
                    client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                    client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    scopes=tokens.get('scope', '').split()
                )
                
                calendar_service = build('calendar', 'v3', credentials=creds)
                
                # Fetch ALL calendars with pagination
                calendars_fetched = 0
                page_token = None
                
                while True:
                    # Request calendar list with pagination
                    request_params = {
                        'showDeleted': False,
                        'showHidden': False,
                        'minAccessRole': 'reader'  # Get all calendars where user has at least read access
                    }
                    if page_token:
                        request_params['pageToken'] = page_token
                    
                    calendar_list = calendar_service.calendarList().list(**request_params).execute()
                    
                    for cal_entry in calendar_list.get('items', []):
                        # Skip if this is the primary calendar (already handled as 'self')
                        if cal_entry.get('primary'):
                            logger.info(f"Skipping primary calendar: {cal_entry.get('summary', '')}")
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
                        sub_account, created = GoogleSubAccount.objects.get_or_create(
                            google_calendar=google_calendar,
                            act_as_email=cal_id,
                            defaults={
                                'act_as_user_id': '',  # Will be populated if needed
                                'relationship': relationship,
                                'active': True,
                                'calendar_name': summary  # Store the human-readable name!
                            }
                        )
                        
                        # Update calendar name if it changed
                        if not created and sub_account.calendar_name != summary:
                            sub_account.calendar_name = summary
                            sub_account.save(update_fields=['calendar_name'])
                        
                        calendars_fetched += 1
                        if created:
                            logger.info(f"Created {relationship} sub-account for calendar: {summary} ({cal_id})")
                        else:
                            logger.info(f"Sub-account already exists for calendar: {summary} ({cal_id})")
                    
                    # Check if there are more pages
                    page_token = calendar_list.get('nextPageToken')
                    if not page_token:
                        break
                
                logger.info(f"Total calendars fetched from Google: {calendars_fetched}")
                    
            except Exception as e:
                logger.error(f"Error discovering shared calendars: {str(e)}", exc_info=True)
                # Continue anyway - at least we have the self account
            
            # Sync calendars from Google
            service.sync_calendars(google_calendar)
            
            # Clean up session state
            del request.session[session_key]
            
            logger.info(f"Successfully connected Google Calendar for {user.email}")
            
            # Redirect to frontend with success
            from django.conf import settings
            frontend_url = f"{settings.BASE_URL}/dashboard/calendar"
            return redirect(frontend_url)
            
        except Exception as e:
            logger.error(f"Google OAuth callback error: {str(e)}")
            return Response({
                'error': 'Failed to complete OAuth flow',
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
            
            # Sync calendars (now returns sub-account sync data)
            service = GoogleCalendarService()
            synced_sub_accounts = service.sync_calendars(google_calendar)
            
            # The service already updates last_sync and sync_errors
            
            return Response({
                'success': True,
                'message': f'Synced {len(synced_sub_accounts)} sub-account calendars',
                'synced_data': synced_sub_accounts,  # Return raw sync data
                'google_calendar': GoogleCalendarSerializer(google_calendar).data
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
    
    @action(detail=False, methods=['post'], url_path='refresh-calendars')
    def refresh_calendars(self, request):
        """Refresh/fetch all calendars from Google (including creating new sub-accounts)"""
        google_calendar_id = request.data.get('google_calendar_id')
        
        if not google_calendar_id:
            return Response({'error': 'google_calendar_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the Google calendar
            google_calendar = GoogleCalendar.objects.get(
                id=google_calendar_id,
                calendar__workspace__users=request.user
            )
            
            # Build credentials
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            
            creds = Credentials(
                token=google_calendar.access_token,
                refresh_token=google_calendar.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=google_calendar.scopes
            )
            
            calendar_service = build('calendar', 'v3', credentials=creds)
            
            # Fetch ALL calendars with pagination
            calendars_fetched = 0
            calendars_created = 0
            page_token = None
            
            while True:
                # Request calendar list with pagination
                request_params = {
                    'showDeleted': False,
                    'showHidden': False,
                    'minAccessRole': 'reader'  # Get all calendars where user has at least read access
                }
                if page_token:
                    request_params['pageToken'] = page_token
                
                calendar_list = calendar_service.calendarList().list(**request_params).execute()
                
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
                    sub_account, created = GoogleSubAccount.objects.get_or_create(
                        google_calendar=google_calendar,
                        act_as_email=cal_id,
                        defaults={
                            'act_as_user_id': '',  # Will be populated if needed
                            'relationship': relationship,
                            'active': True
                        }
                    )
                    
                    calendars_fetched += 1
                    if created:
                        calendars_created += 1
                        logger.info(f"Created {relationship} sub-account for calendar: {summary} ({cal_id})")
                
                # Check if there are more pages
                page_token = calendar_list.get('nextPageToken')
                if not page_token:
                    break
            
            logger.info(f"Refreshed calendars: {calendars_fetched} total, {calendars_created} new")
            
            # Now sync the calendars
            service = GoogleCalendarService()
            synced_sub_accounts = service.sync_calendars(google_calendar)
            
            return Response({
                'success': True,
                'message': f'Fetched {calendars_fetched} calendars ({calendars_created} new), synced {len(synced_sub_accounts)}',
                'calendars_fetched': calendars_fetched,
                'calendars_created': calendars_created,
                'synced_count': len(synced_sub_accounts),
                'google_calendar': GoogleCalendarSerializer(google_calendar).data
            })
            
        except GoogleCalendar.DoesNotExist:
            return Response({'error': 'Google calendar not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Calendar refresh failed: {str(e)}", exc_info=True)
            return Response({
                'error': 'Refresh failed',
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
        # IMPORTANT: Delete the generic Calendar first so it can revoke tokens
        calendar = instance.calendar
        calendar.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


# REMOVED: GoogleSubAccountViewSet
# Sub-accounts are now managed automatically during OAuth callback
# They are created when fetching calendars from Google and should not be manually managed via API
