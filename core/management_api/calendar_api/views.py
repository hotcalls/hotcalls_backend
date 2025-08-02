import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, permission_classes, api_view
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample
from django.db import transaction

from core.models import Calendar, CalendarConfiguration, GoogleCalendarConnection, Workspace, GoogleCalendarMCPAgent
from core.services.google_calendar import GoogleCalendarService, GoogleOAuthService, CalendarServiceFactory
from .serializers import (
    CalendarSerializer, GoogleCalendarConnectionSerializer,
    CalendarConfigurationSerializer, CalendarConfigurationCreateSerializer,
    GoogleOAuthCallbackSerializer, AvailabilityRequestSerializer,
    AvailabilityResponseSerializer, BookingRequestSerializer,
    BookingResponseSerializer, GoogleCalendarMCPAgentListSerializer,
    GoogleCalendarMCPTokenRequestSerializer, GoogleCalendarMCPTokenResponseSerializer
)
from .filters import CalendarFilter, CalendarConfigurationFilter
from .permissions import CalendarPermission, CalendarConfigurationPermission, SuperuserOnlyPermission, GoogleCalendarMCPPermission

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
        description="Update calendar information for calendars in your workspace",
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update calendar",
        description="Update specific fields of a calendar in your workspace",
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="Delete calendar",
        description="Delete a calendar in your workspace",
        tags=["User Management"]
    ),
)
class CalendarViewSet(viewsets.ModelViewSet):
    """
    📅 **Calendar Integration Management with Google Calendar Support**
    
    Manages calendar integrations with workspace-filtered access:
    - **👤 Regular Users**: Can view, create, update, and delete calendars in their workspaces
    - **👔 Staff**: Full calendar administration across all workspaces
    - **🔧 Superusers**: Complete calendar control across all workspaces
    
    **🆕 Google Calendar Integration:**
    - OAuth authentication flow
    - Automatic calendar synchronization
    - Real-time availability checking
    - Event creation capabilities
    """
    queryset = Calendar.objects.all()
    permission_classes = [GoogleCalendarMCPPermission]
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
        # Check if this is an MCP request
        if hasattr(self.request, 'google_mcp_agent'):
            # MCP agents can see all active calendars
            return Calendar.objects.filter(active=True).select_related('workspace').prefetch_related('google_calendar')
            
        user = self.request.user
        if user.is_staff:
            return Calendar.objects.filter(active=True).select_related('workspace').prefetch_related('google_calendar')
        else:
            # Regular users can only see calendars in their workspaces and only active calendars
            return Calendar.objects.filter(
                workspace__users=user,
                active=True
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
            
            # 6. Redirect to frontend after successful OAuth
            from django.shortcuts import redirect
            
            # Redirect to frontend calendar dashboard with success parameters
            success_url = f"http://localhost:5173/dashboard/calendar?oauth_success=true&calendars={len(synced_calendars)}&email={connection.account_email}"
            return redirect(success_url)
            
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
            connections = GoogleCalendarConnection.objects.filter(active=True)
        else:
            user_workspace = self._get_user_workspace(user)
            connections = GoogleCalendarConnection.objects.filter(
                workspace=user_workspace, 
                active=True
            )
        
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
            
            # Deactivate related calendars in the same workspace
            Calendar.objects.filter(
                workspace=connection.workspace,
                provider='google'
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


@extend_schema_view(
    list=extend_schema(
        summary="📋 List calendar configurations",
        description="""
        Retrieve calendar configurations based on your workspace access.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see configurations for calendars in their workspaces
        - **Staff Members**: Can view all configurations in the system
        
        **📊 Response Filtering**:
        - Regular users see only workspace-scoped configurations
        - Staff see all configurations
        """,
        responses={
            200: OpenApiResponse(
                response=CalendarConfigurationSerializer(many=True),
                description="✅ Successfully retrieved calendar configurations"
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="➕ Create calendar configuration",
    description="Create a new calendar configuration for calendars in your workspace",
    request=CalendarConfigurationCreateSerializer,
    responses={201: CalendarConfigurationSerializer},
    tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="📄 Get configuration details",
        description="Retrieve detailed information about a specific calendar configuration",
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="✏️ Update configuration",
        description="Update calendar configuration for calendars in your workspace",
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="📝 Partially update configuration",
        description="Update specific fields of a calendar configuration in your workspace",
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete configuration",
        description="Delete a calendar configuration in your workspace",
        tags=["User Management"]
    ),
)
class CalendarConfigurationViewSet(viewsets.ModelViewSet):
    """
    📋 **Calendar Configuration Management**
    
    Manages calendar configurations with workspace-filtered access:
    - **👤 Regular Users**: Can view, create, update, and delete configurations for calendars in their workspaces
    - **👔 Staff**: Full configuration administration across all workspaces
    
    **⚙️ Configuration Features:**
    - Meeting duration settings
    - Preparation time buffer
    - Working days and hours
    - Calendar conflict checking
    """
    queryset = CalendarConfiguration.objects.all()
    permission_classes = [GoogleCalendarMCPPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CalendarConfigurationFilter
    search_fields = ['calendar__name', 'calendar__workspace__workspace_name']
    ordering_fields = ['duration', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CalendarConfigurationCreateSerializer
        return CalendarConfigurationSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        # Check if this is an MCP request
        if hasattr(self.request, 'google_mcp_agent'):
            # MCP agents can see all calendar configurations
            return CalendarConfiguration.objects.all().select_related('calendar__workspace')
            
        user = self.request.user
        if user.is_staff:
            return CalendarConfiguration.objects.all().select_related('calendar__workspace')
        else:
            # Regular users can only see configurations for calendars in their workspaces
            return CalendarConfiguration.objects.filter(
                calendar__workspace__users=user
            ).select_related('calendar__workspace')
    
    def perform_create(self, serializer):
        """Handle creation with workspace permission check"""
        calendar = serializer.validated_data['calendar']
        user = self.request.user
        
        # Staff can create configurations for any calendar
        if user.is_staff:
            serializer.save()
        else:
            # Regular users can only create configurations for calendars in their workspaces
            if calendar.workspace and user in calendar.workspace.users.all():
                serializer.save()
            else:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You can only create configurations for calendars in your workspace")
        
    @extend_schema(
        summary="🕐 Check Calendar Availability",
        description="""
        Check availability for appointments based on calendar configuration rules.
        
        **📋 Process:**
        - Validates workdays and days_buffer
        - Checks conflict_check_calendars for busy times
        - Calculates available slots considering prep_time
        - Returns available time slots within working hours
        
        **⚙️ Configuration Applied:**
        - Working days and hours (from_time/to_time)
        - Preparation time buffer
        - Days buffer for advance booking
        - Conflict calendar checking
        """,
        request=AvailabilityRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=AvailabilityResponseSerializer,
                description="✅ Availability calculated successfully"
            ),
            400: OpenApiResponse(description="❌ Invalid request data"),
            404: OpenApiResponse(description="❌ Configuration not found"),
            403: OpenApiResponse(description="🚫 No access to this configuration")
        },
        tags=["User Management"]
    )
    @action(detail=True, methods=['post'], url_path='check-availability')
    def check_availability(self, request, pk=None):
        """Check availability for appointments based on calendar configuration"""
        config = self.get_object()  # This handles permissions automatically
        
        # Validate request data
        serializer = AvailabilityRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        date = serializer.validated_data['date']
        duration_minutes = serializer.validated_data['duration_minutes']
        
        try:
            # Validate booking rules (workdays, buffer)
            validation = self._validate_booking_rules(config, date)
            if not validation['valid']:
                return Response({
                    'date': date,
                    'available_slots': [],
                    'busy_periods': [],
                    'config_name': config.name,
                    'total_slots_found': 0,
                    'message': validation['reason']
                })
            
            # Get busy times from conflict calendars
            busy_times = self._get_busy_times_from_conflicts(config, date)
            
            # Calculate available slots
            available_slots = self._calculate_available_slots(config, date, duration_minutes, busy_times)
            
            # Prepare response
            response_data = {
                'date': date,
                'available_slots': available_slots,
                'busy_periods': busy_times,
                'config_name': config.name,
                'total_slots_found': len(available_slots)
            }
            
            logger.info(f"Availability check for config {config.id}: {len(available_slots)} slots found for {date}")
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error checking availability for config {config.id}: {str(e)}")
            return Response({
                'error': 'Failed to check availability',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="📅 Book Appointment",
        description="""
        Book an appointment based on calendar configuration.
        
        **📋 Process:**
        - Double-checks availability (race condition prevention)
        - Creates event in main calendar
        - Applies meeting type specific details (link/address)
        - Sends calendar invitation to attendee
        
        **⚙️ Configuration Applied:**
        - Meeting type (online/in_person/phone)
        - Meeting link or address
        - Calendar for event creation
        """,
        request=BookingRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=BookingResponseSerializer,
                description="✅ Appointment booked successfully"
            ),
            400: OpenApiResponse(description="❌ Invalid request data or time not available"),
            404: OpenApiResponse(description="❌ Configuration not found"),
            403: OpenApiResponse(description="🚫 No access to this configuration")
        },
        tags=["User Management"]
    )
    @action(detail=True, methods=['post'], url_path='book-appointment')
    def book_appointment(self, request, pk=None):
        """Book an appointment based on calendar configuration"""
        config = self.get_object()  # This handles permissions automatically
        
        # Validate request data
        serializer = BookingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        start_time = serializer.validated_data['start_time']
        duration_minutes = serializer.validated_data['duration_minutes']
        title = serializer.validated_data['title']
        attendee_email = serializer.validated_data['attendee_email']
        attendee_name = serializer.validated_data.get('attendee_name')
        description = serializer.validated_data.get('description')
        
        try:
            # Double-check availability (race condition prevention)
            date = start_time.date()
            
            # Validate booking rules
            validation = self._validate_booking_rules(config, date)
            if not validation['valid']:
                return Response({
                    'error': 'Booking rules validation failed',
                    'details': validation['reason']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get current busy times and check if slot is still available
            busy_times = self._get_busy_times_from_conflicts(config, date)
            available_slots = self._calculate_available_slots(config, date, duration_minutes, busy_times)
            
            # Check if requested time slot is available
            requested_time = start_time.strftime('%H:%M:%S')
            slot_available = any(
                slot['start_time'] <= requested_time < slot['end_time'] 
                for slot in available_slots
            )
            
            if not slot_available:
                return Response({
                    'error': 'Time slot no longer available',
                    'details': f'Requested time {requested_time} is not available'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Build event data
            event_data = self._build_event_data(
                config, start_time, duration_minutes, title, 
                attendee_email, attendee_name, description
            )
            
            # Create event in main calendar
            main_calendar = config.calendar
            if not hasattr(main_calendar, 'google_calendar'):
                return Response({
                    'error': 'Calendar configuration error',
                    'details': 'Main calendar has no Google Calendar connection'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            service = CalendarServiceFactory.get_service(main_calendar)
            external_id = main_calendar.google_calendar.external_id
            
            # Create the event
            created_event = service.create_event(external_id, event_data)
            
            # Prepare meeting details for response
            meeting_details = {
                'type': config.meeting_type,
                'duration_minutes': duration_minutes
            }
            
            if config.meeting_type == 'online' and config.meeting_link:
                meeting_details['meeting_link'] = config.meeting_link
            elif config.meeting_type == 'in_person' and config.meeting_address:
                meeting_details['address'] = config.meeting_address
            
            # Prepare response
            end_time = start_time + timedelta(minutes=duration_minutes)
            response_data = {
                'event_id': created_event['id'],
                'calendar_id': external_id,
                'start_time': start_time,
                'end_time': end_time,
                'title': title,
                'attendee_email': attendee_email,
                'meeting_details': meeting_details,
                'config_name': config.name
            }
            
            logger.info(f"Appointment booked successfully: {created_event['id']} for config {config.id}")
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Error booking appointment for config {config.id}: {str(e)}")
            return Response({
                'error': 'Failed to book appointment',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 
    
    def _validate_booking_rules(self, config: CalendarConfiguration, date) -> dict:
        """Validate booking rules (workdays, days_buffer)"""
        # Check if date is in workdays
        weekday = date.strftime('%A').lower()
        if weekday not in [day.lower() for day in config.workdays]:
            return {
                'valid': False,
                'reason': f'Not a working day. Working days: {", ".join(config.workdays)}'
            }
        
        # Check days_buffer
        days_until = (date - timezone.now().date()).days
        if days_until < config.days_buffer:
            return {
                'valid': False,
                'reason': f'Booking must be at least {config.days_buffer} days in advance'
            }
        
        return {'valid': True}
    
    def _get_busy_times_from_conflicts(self, config: CalendarConfiguration, date) -> list:
        """Get busy times from all conflict_check_calendars"""
        busy_times = []
        
        start_datetime = datetime.combine(date, config.from_time)
        end_datetime = datetime.combine(date, config.to_time)
        
        # Make timezone aware
        start_datetime = timezone.make_aware(start_datetime)
        end_datetime = timezone.make_aware(end_datetime)
        
        for calendar_id in config.conflict_check_calendars:
            try:
                conflict_calendar = Calendar.objects.select_related(
                    'google_calendar'
                ).get(id=calendar_id)
                
                if not hasattr(conflict_calendar, 'google_calendar'):
                    logger.warning(f"Calendar {calendar_id} has no google_calendar data")
                    continue
                
                # Get GoogleCalendarService through existing factory
                service = CalendarServiceFactory.get_service(conflict_calendar)
                external_id = conflict_calendar.google_calendar.external_id
                
                # Get busy times for this calendar
                calendar_busy = service.check_availability(external_id, start_datetime, end_datetime)
                
                # Format busy times
                for busy_period in calendar_busy:
                    busy_times.append({
                        'start': busy_period.get('start'),
                        'end': busy_period.get('end'),
                        'calendar_name': conflict_calendar.name
                    })
                    
            except Calendar.DoesNotExist:
                logger.warning(f"Conflict calendar {calendar_id} not found")
                continue
            except Exception as e:
                logger.error(f"Error getting busy times for calendar {calendar_id}: {str(e)}")
                continue
        
        return busy_times
    
    def _calculate_available_slots(self, config: CalendarConfiguration, date, duration_minutes: int, busy_times: list) -> list:
        """Calculate available time slots"""
        from datetime import time, timedelta
        
        slots = []
        current_time = config.from_time
        end_time = config.to_time
        
        while True:
            # Create potential slot
            slot_start = datetime.combine(date, current_time)
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            
            # Check if slot fits within working hours
            if slot_end.time() > end_time:
                break
            
            # Check if slot conflicts with busy times
            is_available = True
            
            for busy_period in busy_times:
                busy_start = busy_period.get('start')
                busy_end = busy_period.get('end')
                
                if isinstance(busy_start, str):
                    busy_start = datetime.fromisoformat(busy_start.replace('Z', '+00:00'))
                if isinstance(busy_end, str):
                    busy_end = datetime.fromisoformat(busy_end.replace('Z', '+00:00'))
                
                # Make timezone aware
                slot_start_aware = timezone.make_aware(slot_start)
                slot_end_aware = timezone.make_aware(slot_end)
                
                # Check for overlap (including prep_time buffer)
                buffer_start = slot_start_aware - timedelta(minutes=config.prep_time)
                
                if (buffer_start < busy_end and slot_end_aware > busy_start):
                    is_available = False
                    break
            
            if is_available:
                slots.append({
                    'start_time': slot_start.strftime('%H:%M:%S'),
                    'end_time': slot_end.strftime('%H:%M:%S'),
                    'start_datetime': slot_start_aware.isoformat(),
                    'end_datetime': slot_end_aware.isoformat()
                })
            
            # Move to next 15-minute interval
            current_time = (datetime.combine(date, current_time) + timedelta(minutes=15)).time()
        
        return slots
    
    def _build_event_data(self, config: CalendarConfiguration, start_time, duration_minutes: int, title: str, attendee_email: str, attendee_name: str = None, description: str = None) -> dict:
        """Build Google Calendar event data from config"""
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Base event data
        event_data = {
            'summary': title,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC'
            },
            'end': {
                'dateTime': end_time.isoformat(), 
                'timeZone': 'UTC'
            },
            'attendees': [{'email': attendee_email}]
        }
        
        # Add attendee name if provided
        if attendee_name:
            event_data['attendees'][0]['displayName'] = attendee_name
        
        # Build description based on config and meeting type
        event_description = f"Booking via {config.name}"
        
        if description:
            event_description += f"\n\n{description}"
        
        # Add meeting type specific details
        if config.meeting_type == 'online' and config.meeting_link:
            event_description += f"\n\nJoin meeting: {config.meeting_link}"
        elif config.meeting_type == 'in_person' and config.meeting_address:
            event_data['location'] = config.meeting_address
            event_description += f"\n\nLocation: {config.meeting_address}"
        elif config.meeting_type == 'phone':
            event_description += "\n\nMeeting Type: Phone Call"
        
        event_data['description'] = event_description
        
        return event_data 


# ===== GOOGLE CALENDAR MCP TOKEN MANAGEMENT =====

@extend_schema_view(
    list=extend_schema(
        summary="📋 List Google Calendar MCP agents",
        description="""
        List all Google Calendar MCP agents (without exposing tokens).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access
        - **✅ Superuser ONLY**: Can view agent list
        
        **📊 Information Shown**:
        - Agent ID and name
        - Creation and expiration dates
        - Token validity status
        - **NO token values exposed**
        """,
        responses={
            200: OpenApiResponse(
                response=GoogleCalendarMCPAgentListSerializer(many=True),
                description="✅ Google Calendar MCP agents retrieved successfully"
            ),
            403: OpenApiResponse(description="🚫 Superuser access required")
        },
        tags=["Google Calendar MCP Token Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete Google Calendar MCP token",
        description="""
        Delete a Google Calendar MCP agent token permanently.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access
        - **✅ Superuser ONLY**: Can delete tokens
        
        **⚠️ Warning**:
        - This permanently deletes the agent token
        - Any MCP systems using this token will lose authentication
        - Cannot be undone - token must be regenerated if needed
        """,
        responses={
            204: OpenApiResponse(description="✅ Token deleted successfully"),
            403: OpenApiResponse(description="🚫 Superuser access required"),
            404: OpenApiResponse(description="🚫 Token not found")
        },
        tags=["Google Calendar MCP Token Management"]
    ),
    create=extend_schema(exclude=True),  # Hidden - use generate_token instead
    update=extend_schema(exclude=True),  # Hidden - tokens cannot be updated
    partial_update=extend_schema(exclude=True),  # Hidden - tokens cannot be updated
)
class GoogleCalendarMCPTokenViewSet(viewsets.ModelViewSet):
    """
    🔐 **Google Calendar MCP Token Management (Superuser Only)**
    
    Manages Google Calendar MCP authentication tokens with strict access control:
    - **🚫 Staff and Regular Users**: No access
    - **✅ Superuser Only**: Can generate and manage tokens
    """
    queryset = GoogleCalendarMCPAgent.objects.all().order_by('-created_at')
    serializer_class = GoogleCalendarMCPAgentListSerializer
    permission_classes = [SuperuserOnlyPermission]
    
    def create(self, request, *args, **kwargs):
        """Block direct creation - use generate_token action instead"""
        return Response(
            {'detail': 'Use /generate_token/ endpoint to create tokens'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def update(self, request, *args, **kwargs):
        """Block updates - tokens should be replaced via generate_token"""
        return Response(
            {'detail': 'Tokens cannot be updated. Use /generate_token/ to replace.'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Block partial updates"""
        return Response(
            {'detail': 'Tokens cannot be updated. Use /generate_token/ to replace.'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    @extend_schema(
        summary="🔑 Generate Google Calendar MCP token",
        description="""
        Generate a new Google Calendar MCP authentication token for an agent.
        
        **🔐 Access Control**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access  
        - **✅ Superuser ONLY**: Can generate tokens
        
        **📝 Token Management**:
        - Each agent name can have only ONE active token
        - If agent already exists, old token is replaced
        - Token expires after 1 year
        - Secure random string generation
        
        **🔄 Replacement Logic**:
        - Existing agent → Replace token, extend expiration
        - New agent → Create new record with fresh token
        
        **🛡️ Security Features**:
        - 64-character URL-safe random tokens
        - Automatic expiration handling
        - Unique constraints on agent names and tokens
        """,
        request=GoogleCalendarMCPTokenRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=GoogleCalendarMCPTokenResponseSerializer,
                description="✅ Token generated successfully"
            ),
            400: OpenApiResponse(description="❌ Validation error"),
            403: OpenApiResponse(description="🚫 Superuser access required")
        },
        tags=["Google Calendar MCP Token Management"]
    )
    @action(detail=False, methods=['post'])
    def generate_token(self, request):
        """
        Generate or replace a Google Calendar MCP authentication token for an agent.
        
        Only superusers can access this endpoint.
        Each agent name can have only one active token.
        """
        serializer = GoogleCalendarMCPTokenRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        agent_name = serializer.validated_data['agent_name']
        
        with transaction.atomic():
            # Check if agent already exists
            try:
                agent = GoogleCalendarMCPAgent.objects.get(name=agent_name)
                # Replace existing token
                agent.token = GoogleCalendarMCPAgent.generate_token()
                agent.expires_at = timezone.now() + timezone.timedelta(days=365)
                agent.save(update_fields=['token', 'expires_at'])
                
            except GoogleCalendarMCPAgent.DoesNotExist:
                # Create new agent
                agent = GoogleCalendarMCPAgent.objects.create(name=agent_name)
        
        response_serializer = GoogleCalendarMCPTokenResponseSerializer(agent)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED) 