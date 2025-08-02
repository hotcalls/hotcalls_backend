import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import Calendar, CalendarConfiguration, GoogleCalendarConnection, Workspace
from core.services.google_calendar import GoogleCalendarService, GoogleOAuthService, CalendarServiceFactory
from .serializers import (
    CalendarSerializer, GoogleCalendarConnectionSerializer,
    CalendarConfigurationSerializer, CalendarConfigurationCreateSerializer,
    CalendarAvailabilityRequestSerializer, CalendarAvailabilityResponseSerializer,
    GoogleOAuthCallbackSerializer, EventCreateSerializer
)
from .filters import CalendarFilter, CalendarConfigurationFilter
from .permissions import CalendarPermission, CalendarConfigurationPermission

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="📅 List calendars",
        description="""
        Retrieve calendars based on your workspace access and role.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see calendars in their workspaces (filtered)
        - **Staff Members**: Can view all calendars in the system
        - **Superusers**: Full access to all calendar data
        
        **📊 Response Filtering**:
        - Regular users see only workspace-scoped calendars
        - Staff/Superusers see all calendars with full configuration
        
        **🎯 Use Cases**:
        - Calendar integration overview
        - Scheduling resource management
        - Workspace calendar inventory
        """,
        responses={
            200: OpenApiResponse(
                response=CalendarSerializer(many=True),
                description="✅ Successfully retrieved calendars based on access level"
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access calendars")
        },
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="Get calendar details",
        description="Retrieve detailed information about a specific calendar with provider details",
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="Update calendar",
        description="Update calendar information (staff only)",
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update calendar",
        description="Update specific fields of a calendar (staff only)",
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="Delete calendar",
        description="Delete a calendar (superuser only)",
        tags=["User Management"]
    ),
)
class CalendarViewSet(viewsets.ModelViewSet):
    """
    📅 **Calendar Integration Management with Google Calendar Support**
    
    Manages calendar integrations with workspace-filtered access:
    - **👤 Regular Users**: Access only calendars in their workspaces
    - **👔 Staff**: Full calendar administration across all workspaces
    - **🔧 Superusers**: Complete calendar control including deletion
    
    **🆕 Google Calendar Integration:**
    - OAuth authentication flow
    - Automatic calendar synchronization
    - Real-time availability checking
    - Event creation capabilities
    """
    queryset = Calendar.objects.all()
    permission_classes = [CalendarPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CalendarFilter
    search_fields = ['name', 'workspace__workspace_name']
    ordering_fields = ['provider', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        return CalendarSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return Calendar.objects.all().select_related('workspace').prefetch_related('google_calendar')
        else:
            # Regular users can only see calendars in their workspaces
            return Calendar.objects.filter(
                workspace__users=user
            ).select_related('workspace').prefetch_related('google_calendar')
    
    # 🎯 GOOGLE OAUTH ENDPOINTS
    
    @extend_schema(
        summary="🔗 Get Google OAuth Authorization URL",
        description="""
        **Generate Google OAuth authorization URL to start OAuth flow**
        
        This endpoint generates the URL where users should be redirected to authorize Google Calendar access.
        
        **📋 Process Flow:**
        1. Frontend calls this endpoint
        2. Backend generates Google OAuth URL with required parameters
        3. Frontend redirects user to the returned URL
        4. User authorizes on Google
        5. Google redirects back to your callback endpoint
        
        **🔐 Parameters:**
        - `state`: Optional CSRF protection parameter
        
        **📊 Response:**
        - `authorization_url`: The URL to redirect user to Google OAuth
        - `state`: The state parameter used (for verification)
        """,
        responses={
            200: OpenApiResponse(
                response={'type': 'object', 'properties': {
                    'authorization_url': {'type': 'string'},
                    'state': {'type': 'string'}
                }},
                description="✅ Authorization URL generated successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            500: OpenApiResponse(description="💥 Server error generating URL")
        },
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='google_auth_url')
    def get_google_auth_url(self, request):
        """
        🎯 OAUTH START POINT - Generate Google OAuth authorization URL
        """
        try:
            # Generate state with user ID for callback identification
            import secrets
            state = secrets.token_urlsafe(32)
            
            # Store user ID in state for callback lookup
            request.session[f'google_oauth_state_{state}'] = {
                'user_id': str(request.user.id),  # Convert UUID to string for JSON serialization
                'created_at': timezone.now().isoformat()
            }
            
            # Generate authorization URL
            authorization_url = GoogleOAuthService.get_authorization_url(state=state)
            
            logger.info(f"Generated Google OAuth URL for user {request.user.email}")
            
            return Response({
                'authorization_url': authorization_url,
                'state': state,
                'message': 'Redirect user to this URL to start Google OAuth flow'
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
        **Handle Google OAuth callback and create calendar connection**
        
        This endpoint is called by Google after user grants permissions.
        
        **📋 Process Flow:**
        1. Receives authorization code from Google
        2. Exchanges code for access & refresh tokens
        3. Creates GoogleCalendarConnection
        4. Fetches and saves user's calendar list
        5. Returns connection details + available calendars
        
        **🔐 Required Parameters:**
        - `code`: Authorization code from Google OAuth
        - `state`: Optional state parameter for security
        
        **📊 Response:**
        - Connection details
        - List of synchronized calendars
        - Success/error status
        """,
        responses={
            200: OpenApiResponse(response=GoogleOAuthCallbackSerializer, description="✅ OAuth successful, connection created"),
            400: OpenApiResponse(description="❌ OAuth failed or missing authorization code"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            500: OpenApiResponse(description="💥 Server error during OAuth process")
        },
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['get'], url_path='google_callback', permission_classes=[AllowAny])
    def google_oauth_callback(self, request):
        """
        🎯 MAIN ENTRY POINT - Handle Google OAuth callback
        This is where our backend picks up the OAuth flow
        """
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        if error:
            logger.warning(f"Google OAuth error: {error}")
            return Response({'error': f'OAuth failed: {error}'}, status=status.HTTP_400_BAD_REQUEST)
            
        if not code:
            logger.warning("No authorization code received in OAuth callback")
            return Response({'error': 'No authorization code received'}, status=status.HTTP_400_BAD_REQUEST)
            
        if not state:
            logger.warning("No state parameter received in OAuth callback")
            return Response({'error': 'No state parameter received'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get user from state
        state_key = f'google_oauth_state_{state}'
        state_data = request.session.get(state_key)
        
        if not state_data:
            logger.warning(f"Invalid or expired state parameter: {state}")
            return Response({'error': 'Invalid or expired OAuth session'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get user from state data
        try:
            from core.models import User
            user = User.objects.get(id=state_data['user_id'])
        except User.DoesNotExist:
            logger.error(f"User not found for OAuth callback: {state_data['user_id']}")
            return Response({'error': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Clean up state from session
        del request.session[state_key]
        
        try:
            # 1. Exchange code for tokens
            credentials = GoogleOAuthService.exchange_code_for_tokens(code)
            
            # 2. Get user info from Google
            user_info = GoogleOAuthService.get_user_info(credentials)
            
            # 3. Get user's workspace
            user_workspace = self._get_user_workspace(user)
            if not user_workspace:
                return Response({
                    'error': 'User must belong to a workspace to connect Google Calendar'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 4. Create or update GoogleCalendarConnection
            connection, created = GoogleCalendarConnection.objects.update_or_create(
                workspace=user_workspace,
                account_email=user_info['email'],
                defaults={
                    'user': user,
                    'refresh_token': credentials.refresh_token,
                    'access_token': credentials.token,
                    'token_expires_at': self._make_timezone_aware(credentials.expiry),
                    'scopes': list(credentials.scopes),
                    'active': True
                }
            )
            
            # 5. Immediately sync calendar list
            service = GoogleCalendarService(connection)
            synced_calendars = service.sync_calendars()
            
            logger.info(f"{'Created' if created else 'Updated'} Google Calendar connection for {user_info['email']}")
            
            # 6. Return success with calendar data
            if request.GET.get('redirect_frontend'):
                # Redirect to frontend with success
                from django.shortcuts import redirect
                frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
                return redirect(f"{frontend_url}/calendar-integration?success=true&calendars={len(synced_calendars)}")
            else:
                # API response (for direct API calls)
                return Response({
                    'success': True,
                    'connection': {
                        'id': connection.id,
                        'account_email': connection.account_email,
                        'calendars_count': len(synced_calendars),
                        'created': created
                    },
                    'calendars': CalendarSerializer(synced_calendars, many=True).data,
                    'message': f'Successfully connected {connection.account_email}'
                })
            
        except Exception as e:
            logger.error(f"Google OAuth callback failed: {str(e)}")
            return Response({
                'error': 'Failed to connect Google Calendar',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_user_workspace(self, user):
        """Get user's workspace - PRODUCTION VERSION"""
        # Get user's workspace via ManyToMany relationship
        user_workspaces = user.mapping_user_workspaces.all()
        
        if user_workspaces.exists():
            return user_workspaces.first()
        else:
            # PRODUCTION: User MUSS ein Workspace haben
            logger.error(f"User {user.email} has no workspace - this should not happen in production")
            raise ValueError(f"User {user.email} has no workspace assigned. Please contact support.")
    
    def _make_timezone_aware(self, dt):
        """Convert timezone-naive datetime to timezone-aware UTC datetime"""
        if dt is None:
            return None
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            # Assume UTC if no timezone info
            return dt.replace(tzinfo=dt_timezone.utc)
        return dt
    
    # 🔗 GOOGLE CONNECTION MANAGEMENT
    
    @extend_schema(
        summary="📋 List Google Calendar Connections",
        description="Get all Google Calendar connections for the user's workspace",
        responses={200: OpenApiResponse(response=GoogleCalendarConnectionSerializer(many=True))},
        tags=["Google Calendar"]
    )
    @action(detail=False, methods=['get'], url_path='google_connections')
    def list_google_connections(self, request):
        """List Google Calendar connections for workspace"""
        user = request.user
        if user.is_staff:
            connections = GoogleCalendarConnection.objects.all()
        else:
            user_workspace = self._get_user_workspace(user)
            connections = GoogleCalendarConnection.objects.filter(workspace=user_workspace)
        
        serializer = GoogleCalendarConnectionSerializer(connections, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="🔄 Refresh Google Connection",
        description="Refresh tokens and sync calendars for a Google connection",
        responses={200: OpenApiResponse(response=GoogleCalendarConnectionSerializer)},
        tags=["Google Calendar"]
    )
    @action(detail=True, methods=['post'], url_path='google_refresh')
    def refresh_google_connection(self, request, pk=None):
        """Refresh Google connection tokens and sync calendars"""
        try:
            connection = GoogleCalendarConnection.objects.get(pk=pk)
            
            # Check permissions
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            service = GoogleCalendarService(connection)
            
            # Test and refresh connection
            test_result = service.test_connection()
            if not test_result['success']:
                return Response({
                    'error': 'Connection test failed',
                    'details': test_result.get('error')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Sync calendars
            synced_calendars = service.sync_calendars()
            
            return Response({
                'success': True,
                'connection': GoogleCalendarConnectionSerializer(connection).data,
                'calendars_synced': len(synced_calendars),
                'message': f'Successfully refreshed connection for {connection.account_email}'
            })
            
        except GoogleCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Failed to refresh Google connection: {str(e)}")
            return Response({
                'error': 'Failed to refresh connection',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🔌 Disconnect Google Calendar",
        description="Revoke Google tokens and deactivate connection",
        tags=["Google Calendar"]
    )
    @action(detail=True, methods=['post'], url_path='google_disconnect')
    def disconnect_google_connection(self, request, pk=None):
        """Disconnect Google Calendar connection"""
        try:
            connection = GoogleCalendarConnection.objects.get(pk=pk)
            
            # Check permissions
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            # Revoke token at Google
            revoked = GoogleOAuthService.revoke_token(connection.refresh_token)
            
            # Deactivate connection and related calendars
            connection.active = False
            connection.save()
            
            # Deactivate related calendars
            Calendar.objects.filter(
                google_calendar__connection=connection
            ).update(active=False)
            
            logger.info(f"Disconnected Google Calendar for {connection.account_email}")
            
            return Response({
                'success': True,
                'message': f'Successfully disconnected {connection.account_email}',
                'token_revoked': revoked
            })
            
        except GoogleCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Failed to disconnect Google connection: {str(e)}")
            return Response({
                'error': 'Failed to disconnect',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # 📊 CALENDAR FUNCTIONALITY
    
    @extend_schema(
        summary="Get calendar configurations",
        description="Get all configurations for a specific calendar",
        tags=["User Management"]
    )
    @action(detail=True, methods=['get'])
    def configurations(self, request, pk=None):
        """Get all configurations for a specific calendar"""
        calendar = self.get_object()
        configurations = calendar.configurations.all()
        serializer = CalendarConfigurationSerializer(configurations, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="🧪 Test calendar connection",
        description="Test the connection to the calendar service",
        tags=["User Management"]
    )
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test calendar connection"""
        calendar = self.get_object()
        
        try:
            service = CalendarServiceFactory.get_service(calendar)
            result = service.test_connection()
            
            return Response({
                'calendar_id': calendar.id,
                'provider': calendar.provider,
                'name': calendar.name,
                **result,
                'last_tested': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Calendar connection test failed for {calendar.id}: {str(e)}")
            return Response({
                'calendar_id': calendar.id,
                'provider': calendar.provider,
                'connection_status': 'error',
                'error': str(e),
                'last_tested': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="🗓️ Create calendar event",
        description="Create an event in the calendar",
        request=EventCreateSerializer,
        tags=["User Management"]
    )
    @action(detail=True, methods=['post'], url_path='create-event')
    def create_event(self, request, pk=None):
        """Create an event in the calendar"""
        calendar = self.get_object()
        serializer = EventCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = CalendarServiceFactory.get_service(calendar)
            
            # Prepare event data for Google Calendar API
            event_data = {
                'summary': serializer.validated_data['summary'],
                'description': serializer.validated_data.get('description', ''),
                'start': {
                    'dateTime': serializer.validated_data['start_time'].isoformat(),
                    'timeZone': 'UTC'
                },
                'end': {
                    'dateTime': serializer.validated_data['end_time'].isoformat(),
                    'timeZone': 'UTC'
                }
            }
            
            # Add attendees if provided
            if serializer.validated_data.get('attendee_emails'):
                event_data['attendees'] = [
                    {'email': email} for email in serializer.validated_data['attendee_emails']
                ]
            
            event = service.create_event(
                serializer.validated_data['calendar_id'],
                event_data
            )
            
            return Response({
                'success': True,
                'event': {
                    'id': event['id'],
                    'summary': event['summary'],
                    'start': event['start'],
                    'end': event['end'],
                    'html_link': event.get('htmlLink')
                },
                'message': 'Event created successfully'
            })
            
        except Exception as e:
            logger.error(f"Failed to create event in calendar {calendar.id}: {str(e)}")
            return Response({
                'error': 'Failed to create event',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema_view(
    list=extend_schema(
        summary="List calendar configurations",
        description="Retrieve a list of all calendar configurations with filtering capabilities",
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="Create a new calendar configuration",
        description="Create a new calendar configuration (staff only)",
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="Get configuration details",
        description="Retrieve detailed information about a specific calendar configuration",
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="Update configuration",
        description="Update all fields of a calendar configuration (staff only)",
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update configuration",
        description="Update specific fields of a calendar configuration (staff only)",
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="Delete configuration",
        description="Delete a calendar configuration (staff only)",
        tags=["User Management"]
    ),
)
class CalendarConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CalendarConfiguration model operations
    
    Provides CRUD operations for calendar configurations:
    - Users can view configurations for calendars in their workspaces
    - Staff can create/modify/delete configurations
    """
    queryset = CalendarConfiguration.objects.all()
    permission_classes = [CalendarConfigurationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CalendarConfigurationFilter
    search_fields = ['calendar__name', 'calendar__workspace__workspace_name']
    ordering_fields = ['duration', 'prep_time', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CalendarConfigurationCreateSerializer
        return CalendarConfigurationSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return CalendarConfiguration.objects.all().select_related('calendar__workspace')
        else:
            # Regular users can only see configurations for calendars in their workspaces
            return CalendarConfiguration.objects.filter(
                calendar__workspace__users=user
            ).select_related('calendar__workspace')
    
    @extend_schema(
        summary="🔍 Check availability",
        description="Check available time slots for a specific date using real Google Calendar data",
        request=CalendarAvailabilityRequestSerializer,
        responses={200: OpenApiResponse(response=CalendarAvailabilityResponseSerializer)},
        tags=["User Management"]
    )
    @action(detail=True, methods=['post'])
    def check_availability(self, request, pk=None):
        """Check availability for a specific configuration and date using real Google Calendar API"""
        configuration = self.get_object()
        serializer = CalendarAvailabilityRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            date = serializer.validated_data['date']
            duration_minutes = serializer.validated_data['duration_minutes']
            
            # Get calendar service
            calendar = configuration.calendar
            service = CalendarServiceFactory.get_service(calendar)
            
            # Check if it's a Google calendar and get the external ID
            if calendar.provider == 'google':
                google_calendar = calendar.google_calendar
                calendar_id = google_calendar.external_id
            else:
                return Response({
                    'error': 'Real availability checking only supported for Google Calendar'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Define time window for the day
            start_datetime = datetime.combine(date, configuration.from_time)
            end_datetime = datetime.combine(date, configuration.to_time)
            
            # Get busy times from Google Calendar
            busy_times = service.check_availability(calendar_id, start_datetime, end_datetime)
            
            # Calculate available slots
            available_slots = self._calculate_available_slots(
                start_datetime, end_datetime, busy_times, duration_minutes
            )
            
            response_data = {
                'date': date,
                'available_slots': available_slots,
                'calendar_config_id': configuration.id,
                'busy_times': busy_times
            }
            
            response_serializer = CalendarAvailabilityResponseSerializer(response_data)
            return Response(response_serializer.data)
            
        except Exception as e:
            logger.error(f"Failed to check availability for config {configuration.id}: {str(e)}")
            return Response({
                'error': 'Failed to check availability',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _calculate_available_slots(self, start_time, end_time, busy_times, duration_minutes):
        """Calculate available time slots based on busy times"""
        available_slots = []
        current_time = start_time
        slot_duration = timedelta(minutes=duration_minutes)
        
        # Convert busy times to datetime objects
        busy_periods = []
        for busy in busy_times:
            busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
            busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
            busy_periods.append((busy_start, busy_end))
        
        # Sort busy periods
        busy_periods.sort(key=lambda x: x[0])
        
        while current_time + slot_duration <= end_time:
            slot_end = current_time + slot_duration
            
            # Check if this slot conflicts with any busy period
            is_available = True
            for busy_start, busy_end in busy_periods:
                if (current_time < busy_end and slot_end > busy_start):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append({
                    'start_time': current_time.time().isoformat(),
                    'end_time': slot_end.time().isoformat(),
                    'available': True
                })
            
            current_time += timedelta(minutes=30)  # 30-minute intervals
        
        return available_slots 