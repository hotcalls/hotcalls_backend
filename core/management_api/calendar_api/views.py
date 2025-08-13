import logging
import os
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

from core.models import Calendar, CalendarConfiguration, GoogleCalendarConnection, Workspace
from core.models import MicrosoftCalendarConnection, MicrosoftCalendar  # type: ignore
from core.services.google_calendar import GoogleCalendarService, GoogleOAuthService, CalendarServiceFactory
from core.services.microsoft_calendar import MicrosoftOAuthService, MicrosoftCalendarService  # type: ignore
from .serializers import (
    CalendarSerializer, GoogleCalendarConnectionSerializer,
    CalendarConfigurationSerializer, CalendarConfigurationCreateSerializer,
    GoogleOAuthCallbackSerializer, AvailabilityRequestSerializer,
    AvailabilityResponseSerializer, BookingRequestSerializer,
    BookingResponseSerializer
)
from .filters import CalendarFilter, CalendarConfigurationFilter
from .permissions import CalendarPermission, CalendarConfigurationPermission, SuperuserOnlyPermission, CalendarLiveKitPermission

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
    permission_classes = [CalendarLiveKitPermission]
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
            return Calendar.objects.filter(active=True).select_related('workspace').prefetch_related('google_calendar', 'microsoft_calendar')

        user = self.request.user
        # Superusers may see all calendars; everyone else is scoped to their workspaces
        if user.is_superuser:
            return Calendar.objects.filter(active=True).select_related('workspace').prefetch_related('google_calendar', 'microsoft_calendar')

        # Staff and regular users: only calendars in the user's workspaces
        return Calendar.objects.filter(
            workspace__users=user,
            active=True
        ).select_related('workspace').prefetch_related('google_calendar', 'microsoft_calendar')
    
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
    
    # 🔗 MICROSOFT OAUTH ENDPOINTS
    @extend_schema(
        summary="🔗 Get Microsoft OAuth Authorization URL",
        description="Generate Microsoft OAuth authorization URL (PKCE) to start OAuth flow",
        responses={200: {'type': 'object', 'properties': {'authorization_url': {'type': 'string'}, 'state': {'type': 'string'}}}},
        tags=["Microsoft Calendar"]
    )
    @action(detail=False, methods=['post'], url_path='microsoft_auth_url')
    def get_microsoft_auth_url(self, request):
        try:
            import secrets, hashlib, base64
            intent = request.data.get('intent')
            state = secrets.token_urlsafe(32)
            code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('utf-8')
            code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')
            request.session[f'ms_oauth_state_{state}'] = {
                'user_id': str(request.user.id),
                'code_verifier': code_verifier,
                'intent': intent,
                'created_at': timezone.now().isoformat()
            }
            authorization_url = MicrosoftOAuthService.build_authorize_url(state=state, code_challenge=code_challenge, intent=intent)
            return Response({'authorization_url': authorization_url, 'state': state})
        except Exception as e:
            logger.error(f"Failed to generate Microsoft OAuth URL: {str(e)}")
            return Response({'error': 'Failed to generate authorization URL', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="🔗 Microsoft OAuth Callback",
        description="Handle Microsoft OAuth callback, create connection and sync calendars",
        tags=["Microsoft Calendar"]
    )
    @action(detail=False, methods=['get'], url_path='microsoft_callback', permission_classes=[AllowAny])
    def microsoft_oauth_callback(self, request):
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        if error:
            return Response({'error': f'OAuth failed: {error}'}, status=status.HTTP_400_BAD_REQUEST)
        if not code or not state:
            return Response({'error': 'Missing code or state'}, status=status.HTTP_400_BAD_REQUEST)
        state_key = f'ms_oauth_state_{state}'
        state_data = request.session.get(state_key)
        if not state_data:
            return Response({'error': 'Invalid or expired OAuth session'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from core.models import User
            user = User.objects.get(id=state_data['user_id'])
        except Exception:
            return Response({'error': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)
        code_verifier = state_data.get('code_verifier')
        try:
            token = MicrosoftOAuthService.exchange_code_for_tokens(code, code_verifier)
            access_token = token.get('access_token')
            refresh_token = token.get('refresh_token')
            expires_in = int(token.get('expires_in', 3600))
            token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            # Try to decode id_token to get tid/oid
            tenant_id = ''
            try:
                id_token = token.get('id_token')
                if id_token:
                    import base64, json
                    parts = id_token.split('.')
                    if len(parts) >= 2:
                        payload = parts[1] + '=='
                        data = json.loads(base64.urlsafe_b64decode(payload.encode('utf-8')).decode('utf-8'))
                        tenant_id = data.get('tid', '') or ''
            except Exception:
                tenant_id = ''
            headers = {'Authorization': f'Bearer {access_token}'}
            import requests
            me = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers, timeout=30).json()
            mailbox = requests.get('https://graph.microsoft.com/v1.0/me/mailboxSettings', headers=headers, timeout=30).json()
            user_workspace = self._get_user_workspace(user)
            if not user_workspace:
                return Response({'error': 'User must belong to a workspace'}, status=status.HTTP_400_BAD_REQUEST)
            connection, created = MicrosoftCalendarConnection.objects.update_or_create(
                workspace=user_workspace,
                primary_email=me.get('userPrincipalName') or me.get('mail') or '',
                defaults={
                    'user': user,
                    'tenant_id': tenant_id,
                    'ms_user_id': me.get('id', ''),
                    'display_name': me.get('displayName', ''),
                    'timezone_windows': mailbox.get('timeZone', '') or mailbox.get('workingHours', {}).get('timeZone', {}).get('name', ''),
                    'refresh_token': refresh_token or '',
                    'access_token': access_token or '',
                    'token_expires_at': token_expires_at,
                    'scopes_granted': getattr(settings, 'MS_SCOPES', []),
                    'active': True,
                }
            )
            ms_service = MicrosoftCalendarService(connection)
            ms_service.sync_calendars()
            try:
                del request.session[state_key]
            except Exception:
                pass
            from django.shortcuts import redirect
            frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
            success_url = f"{frontend_url}/dashboard/calendar?oauth_success=true&provider=microsoft&email={connection.primary_email}"
            return redirect(success_url)
        except Exception as e:
            logger.error(f"Microsoft OAuth callback failed: {str(e)}")
            return Response({'error': 'Failed to connect Microsoft 365', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="📋 List Microsoft Calendar Connections", tags=["Microsoft Calendar"]) 
    @action(detail=False, methods=['get'], url_path='microsoft_connections')
    def list_microsoft_connections(self, request):
        user = request.user
        if user.is_staff:
            connections = MicrosoftCalendarConnection.objects.filter(active=True)
        else:
            user_workspace = self._get_user_workspace(user)
            connections = MicrosoftCalendarConnection.objects.filter(workspace=user_workspace, active=True)
        data = [{
            'id': str(c.id),
            'workspace': str(c.workspace.id),
            'primary_email': c.primary_email,
            'display_name': c.display_name,
            'timezone_windows': c.timezone_windows,
            'active': c.active,
            'last_sync': c.last_sync,
            'created_at': c.created_at,
        } for c in connections]
        return Response(data)

    @extend_schema(summary="🔌 Disconnect Microsoft Calendar", tags=["Microsoft Calendar"]) 
    @action(detail=True, methods=['post'], url_path='microsoft_disconnect')
    def disconnect_microsoft_connection(self, request, pk=None):
        try:
            connection = MicrosoftCalendarConnection.objects.get(pk=pk)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            # Try to delete provider subscriptions
            from core.models import MicrosoftSubscription
            subs = MicrosoftSubscription.objects.filter(connection=connection)
            for sub in subs:
                try:
                    ms = MicrosoftCalendarService(connection)
                    ms._request('DELETE', f'https://graph.microsoft.com/v1.0/subscriptions/{sub.subscription_id}')
                except Exception:
                    pass
                sub.delete()
            connection.active = False
            connection.save(update_fields=['active', 'updated_at'])
            Calendar.objects.filter(workspace=connection.workspace, provider='outlook').update(active=False)
            return Response({'success': True, 'message': f'Disconnected {connection.primary_email}'})
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Failed to disconnect Microsoft connection: {str(e)}")
            return Response({'error': 'Failed to disconnect', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="🔄 Refresh Microsoft Connection", tags=["Microsoft Calendar"]) 
    @action(detail=True, methods=['post'], url_path='microsoft_refresh')
    def refresh_microsoft_connection(self, request, pk=None):
        try:
            connection = MicrosoftCalendarConnection.objects.get(pk=pk)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            if not connection.refresh_token:
                return Response({'error': 'No refresh token stored'}, status=status.HTTP_400_BAD_REQUEST)
            token = MicrosoftOAuthService.refresh_tokens(connection.refresh_token)
            connection.access_token = token.get('access_token')
            connection.refresh_token = token.get('refresh_token') or connection.refresh_token
            connection.token_expires_at = timezone.now() + timedelta(seconds=int(token.get('expires_in', 3600)))
            connection.save(update_fields=['access_token', 'refresh_token', 'token_expires_at', 'updated_at'])
            ms_service = MicrosoftCalendarService(connection)
            synced = ms_service.sync_calendars()
            return Response({'success': True, 'calendars_synced': len(synced)})
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Failed to refresh Microsoft connection: {str(e)}")
            return Response({'error': 'Failed to refresh connection', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="📅 List Microsoft calendars", tags=["Microsoft Calendar"]) 
    @action(detail=False, methods=['get'], url_path='microsoft_calendars')
    def list_microsoft_calendars(self, request):
        connection_id = request.GET.get('connection_id')
        if not connection_id:
            return Response({'error': 'connection_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            connection = MicrosoftCalendarConnection.objects.get(id=connection_id)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            calendars = MicrosoftCalendar.objects.filter(connection=connection)
            items = [{
                'id': mc.external_id,
                'name': mc.calendar.name,
                'is_primary': mc.primary,
                'owner_email': connection.primary_email,
                'can_edit': mc.can_edit,
            } for mc in calendars]
            return Response(items)
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(summary="Save Microsoft calendar settings", tags=["Microsoft Calendar"]) 
    @action(detail=True, methods=['post'], url_path='settings')
    def save_microsoft_settings(self, request, pk=None):
        try:
            connection = MicrosoftCalendarConnection.objects.get(pk=pk)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            # Store settings on a generic per-workspace basis using CalendarConfiguration or a simple dict field
            # Keeping it simple: accept and echo back; UI persists via existing config models typically
            settings_payload = {
                'target_calendar_id': request.data.get('target_calendar_id'),
                'conflict_calendar_ids': request.data.get('conflict_calendar_ids', []),
                'timezone_windows': request.data.get('timezone_windows'),
                'working_hours': request.data.get('working_hours'),
                'default_duration': request.data.get('default_duration'),
                'buffer_before': request.data.get('buffer_before'),
                'buffer_after': request.data.get('buffer_after'),
                'min_notice': request.data.get('min_notice'),
                'max_advance_days': request.data.get('max_advance_days'),
                'teams_default': bool(request.data.get('teams_default', False)),
            }
            return Response({'saved': True, 'settings': settings_payload})
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(summary="Subscribe to Microsoft event notifications", tags=["Microsoft Calendar"]) 
    @action(detail=True, methods=['post'], url_path='microsoft_subscribe')
    def microsoft_subscribe(self, request, pk=None):
        try:
            connection = MicrosoftCalendarConnection.objects.get(pk=pk)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            client_state = request.data.get('clientState', '')
            notification_url = request.data.get('notificationUrl')
            ms = MicrosoftCalendarService(connection)
            sub = ms.create_subscription(client_state=client_state, notification_url=notification_url)
            return Response(sub)
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Microsoft subscribe failed: {str(e)}")
            return Response({'error': 'Failed to subscribe', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Renew Microsoft subscription", tags=["Microsoft Calendar"]) 
    @action(detail=True, methods=['post'], url_path='microsoft_subscribe_renew')
    def microsoft_subscribe_renew(self, request, pk=None):
        try:
            from core.models import MicrosoftSubscription
            connection = MicrosoftCalendarConnection.objects.get(pk=pk)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            sub_id = request.data.get('subscription_id')
            if not sub_id:
                # pick the first subscription for this connection
                sub = MicrosoftSubscription.objects.filter(connection=connection).order_by('-expiration_at').first()
                if not sub:
                    return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)
                sub_id = sub.subscription_id
            ms = MicrosoftCalendarService(connection)
            data = ms.renew_subscription(sub_id)
            return Response(data)
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Microsoft renew subscription failed: {str(e)}")
            return Response({'error': 'Failed to renew subscription', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            from django.conf import settings
            
            # Get frontend URL from environment or fallback to localhost for development
            frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
            
            # Redirect to frontend calendar dashboard with success parameters
            success_url = f"{frontend_url}/dashboard/calendar?oauth_success=true&calendars={len(synced_calendars)}&email={connection.account_email}"
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

    # ===== Microsoft Events (CRUD) =====
    @extend_schema(summary="Create Microsoft event", tags=["Microsoft Calendar"])
    @action(detail=True, methods=['post'], url_path='events')
    def create_microsoft_event(self, request, pk=None):
        connection_id = pk
        calendar_id = request.data.get('calendar_id')
        if not connection_id or not calendar_id:
            return Response({'error': 'connectionId and calendar_id are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            connection = MicrosoftCalendarConnection.objects.get(id=connection_id)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            payload = {
                'subject': request.data.get('subject'),
                'body': request.data.get('body', ''),
                'start': request.data.get('start'),
                'end': request.data.get('end'),
                'attendees': request.data.get('attendees', []),
                'location': request.data.get('location'),
                'teams': bool(request.data.get('teams', False)),
            }
            ms = MicrosoftCalendarService(connection)
            event = ms.create_event(calendar_id, payload, send_invitations=str(request.GET.get('sendInvitations', 'true')).lower() == 'true')
            return Response(event, status=status.HTTP_201_CREATED)
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Create Microsoft event failed: {str(e)}")
            return Response({'error': 'Failed to create event', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Update Microsoft event", tags=["Microsoft Calendar"])
    @action(detail=True, methods=['patch'], url_path='events/(?P<event_id>[^/.]+)')
    def update_microsoft_event(self, request, pk=None, event_id=None):
        connection_id = pk
        calendar_id = request.data.get('calendar_id')
        if not connection_id or not calendar_id:
            return Response({'error': 'connectionId and calendar_id are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            connection = MicrosoftCalendarConnection.objects.get(id=connection_id)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            updates = {
                k: request.data[k]
                for k in ['subject', 'body', 'start', 'end', 'attendees', 'location']
                if k in request.data
            }
            ms = MicrosoftCalendarService(connection)
            event = ms.update_event(calendar_id, event_id, updates, send_updates=request.GET.get('sendUpdates', 'all'))
            return Response(event)
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Update Microsoft event failed: {str(e)}")
            return Response({'error': 'Failed to update event', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(summary="Delete Microsoft event", tags=["Microsoft Calendar"])
    @action(detail=True, methods=['delete'], url_path='events/(?P<event_id>[^/.]+)')
    def delete_microsoft_event(self, request, pk=None, event_id=None):
        connection_id = pk
        calendar_id = request.GET.get('calendar_id')
        if not connection_id or not calendar_id:
            return Response({'error': 'connectionId and calendar_id are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            connection = MicrosoftCalendarConnection.objects.get(id=connection_id)
            if not request.user.is_staff and connection.workspace != self._get_user_workspace(request.user):
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            ms = MicrosoftCalendarService(connection)
            ok = ms.delete_event(calendar_id, event_id, send_cancellation=str(request.GET.get('sendCancellation', 'true')).lower() == 'true')
            return Response({'deleted': ok})
        except MicrosoftCalendarConnection.DoesNotExist:
            return Response({'error': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Delete Microsoft event failed: {str(e)}")
            return Response({'error': 'Failed to delete event', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="📊 Google Calendar Health Status",
        description="""
        Get comprehensive health status of all Google Calendar connections.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access  
        - **✅ Superuser ONLY**: Can view health status
        
        **📊 Information Provided**:
        - Token expiry status for all calendars
        - Health statistics and summary
        - Calendars requiring attention
        - Automatic recommendations
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Health status retrieved successfully"
            ),
            403: OpenApiResponse(description="🚫 Access denied - Superuser required")
        },
        tags=["System Health"]
    )
    @action(detail=False, methods=['get'], url_path='google_health')
    def google_calendar_health(self, request):
        """Get Google Calendar health status (Superuser only)"""
        # Superuser only check
        if not request.user.is_superuser:
            return Response({
                'error': 'Access denied',
                'details': 'Superuser access required for health monitoring'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            from core.models import GoogleCalendar
            from datetime import timedelta
            
            now = timezone.now()
            all_calendars = GoogleCalendar.objects.all()
            
            health_data = {
                'timestamp': now.isoformat(),
                'total_calendars': all_calendars.count(),
                'healthy': 0,
                'expiring_soon': 0,  # Within 24 hours
                'expired': 0,
                'missing_tokens': 0,
                'calendar_details': [],
                'recommendations': []
            }
            
            for calendar in all_calendars:
                details = self._analyze_calendar_health(calendar, now)
                health_data['calendar_details'].append(details)
                health_data[details['status']] += 1
            
            # Generate recommendations
            health_data['recommendations'] = self._generate_health_recommendations(health_data)
            
            logger.info(f"Google Calendar health check completed: {health_data['healthy']}/{health_data['total_calendars']} healthy")
            
            return Response(health_data)
            
        except Exception as e:
            logger.error(f"Google Calendar health check failed: {str(e)}")
            return Response({
                'error': 'Health check failed',
                'details': str(e),
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _analyze_calendar_health(self, calendar, now):
        """Analyze the health of a single Google Calendar"""
        details = {
            'calendar_id': str(calendar.calendar.id),
            'calendar_name': calendar.calendar.name,
            'external_id': calendar.external_id,
            'status': 'healthy',
            'issue': None,
            'expires_at': calendar.token_expires_at.isoformat() if calendar.token_expires_at else None,
            'time_until_expiry': None,
            'needs_action': False
        }
        
        # Check for missing tokens
        if not calendar.access_token or not calendar.refresh_token:
            details['status'] = 'missing_tokens'
            details['issue'] = 'Missing access or refresh token - requires re-authorization'
            details['needs_action'] = True
            return details
        
        # Check expiry status
        if not calendar.token_expires_at:
            details['status'] = 'missing_tokens'
            details['issue'] = 'No token expiry time set'
            details['needs_action'] = True
            return details
        
        time_diff = calendar.token_expires_at - now
        
        if calendar.token_expires_at < now:
            details['status'] = 'expired'
            details['issue'] = f'Token expired {abs(time_diff)} ago'
            details['needs_action'] = True
        elif calendar.token_expires_at < now + timedelta(hours=24):
            details['status'] = 'expiring_soon'
            details['issue'] = f'Token expires in {time_diff}'
            details['time_until_expiry'] = str(time_diff)
            details['needs_action'] = True
        else:
            details['time_until_expiry'] = str(time_diff)
        
        return details
    
    def _generate_health_recommendations(self, health_data):
        """Generate actionable recommendations based on health data"""
        recommendations = []
        
        if health_data['expired'] > 0:
            recommendations.append({
                'priority': 'high',
                'action': 'refresh_expired_tokens',
                'message': f"{health_data['expired']} calendars have expired tokens",
                'command': 'python manage.py google_calendar_health --refresh-tokens'
            })
        
        if health_data['missing_tokens'] > 0:
            recommendations.append({
                'priority': 'high', 
                'action': 'reauthorize_calendars',
                'message': f"{health_data['missing_tokens']} calendars need re-authorization",
                'command': 'Users must reconnect their Google Calendar accounts'
            })
        
        if health_data['expiring_soon'] > 0:
            recommendations.append({
                'priority': 'medium',
                'action': 'proactive_refresh',
                'message': f"{health_data['expiring_soon']} calendars expire within 24 hours",
                'command': 'Automatic refresh should handle these, monitor closely'
            })
        
        unhealthy_count = health_data['expired'] + health_data['missing_tokens']
        total_count = health_data['total_calendars']
        
        if unhealthy_count == 0:
            recommendations.append({
                'priority': 'info',
                'action': 'all_healthy',
                'message': f"✅ All {total_count} Google Calendar connections are healthy",
                'command': None
            })
        elif unhealthy_count > total_count * 0.5:  # More than 50% unhealthy
            recommendations.append({
                'priority': 'critical',
                'action': 'system_wide_issue',
                'message': f"⚠️ {unhealthy_count}/{total_count} calendars are unhealthy - investigate system-wide issues",
                'command': 'Check Google API credentials and quotas'
            })
        
        return recommendations 


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
    permission_classes = [CalendarLiveKitPermission]
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
                    'message': validation['reason'],
                    'calendar_health': {'status': 'rules_violation', 'message': validation['reason']}
                })
            
            # Get busy times from conflict calendars with enhanced error tracking
            busy_times_result = self._get_busy_times_from_conflicts_with_health(config, date)
            busy_times = busy_times_result['busy_times']
            calendar_health = busy_times_result['health_status']
            
            # Calculate available slots
            available_slots = self._calculate_available_slots(config, date, duration_minutes, busy_times)
            
            # Prepare response with health information
            response_data = {
                'date': date,
                'available_slots': available_slots,
                'busy_periods': busy_times,
                'config_name': config.name,
                'total_slots_found': len(available_slots),
                'calendar_health': calendar_health
            }
            
            # Add warnings if some calendars failed
            if calendar_health['failed_calendars']:
                response_data['warnings'] = [
                    f"Could not check availability for {len(calendar_health['failed_calendars'])} calendars: {', '.join(calendar_health['failed_calendars'])}"
                ]
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error checking availability for config {config.id}: {str(e)}")
            
            # Provide more specific error information
            error_response = {
                'error': 'Failed to check availability',
                'details': str(e),
                'config_name': config.name,
                'date': date,
                'calendar_health': {
                    'status': 'system_error',
                    'message': 'Unexpected system error occurred'
                }
            }
            
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
                    'details': validation['reason'],
                    'config_name': config.name
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get current busy times and check if slot is still available
            busy_times_result = self._get_busy_times_from_conflicts_with_health(config, date)
            busy_times = busy_times_result['busy_times']
            calendar_health = busy_times_result['health_status']
            
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
                    'details': f'Requested time {requested_time} is not available',
                    'calendar_health': calendar_health,
                    'config_name': config.name
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check main calendar health before attempting to book
            main_calendar = config.calendar
            # Verify main calendar tokens based on provider
            if main_calendar.provider == 'google':
                if not hasattr(main_calendar, 'google_calendar'):
                    return Response({'error': 'Calendar configuration error', 'details': 'Missing Google calendar data', 'config_name': config.name}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                conn_ok = bool(main_calendar.google_calendar.connection and main_calendar.google_calendar.connection.access_token)
            else:
                if not hasattr(main_calendar, 'microsoft_calendar'):
                    return Response({'error': 'Calendar configuration error', 'details': 'Missing Microsoft calendar data', 'config_name': config.name}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                conn_ok = bool(main_calendar.microsoft_calendar.connection and main_calendar.microsoft_calendar.connection.access_token)
            if not conn_ok:
                return Response({
                    'error': 'Main calendar authentication required',
                    'details': f'Calendar "{main_calendar.name}" needs re-authorization',
                    'config_name': config.name,
                    'requires_reauth': True
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Build event data
            event_data = self._build_event_data(
                config, start_time, duration_minutes, title, 
                attendee_email, attendee_name, description
            )
            
            # Create event in main calendar
            try:
                service = CalendarServiceFactory.get_service(main_calendar)
                external_id = (
                    main_calendar.google_calendar.external_id if main_calendar.provider == 'google'
                    else main_calendar.microsoft_calendar.external_id
                )
                
                # Create the event
                created_event = service.create_event(external_id, event_data)
                
            except ValueError as e:
                # Handle OAuth/token errors for main calendar
                error_msg = str(e)
                if "Missing tokens" in error_msg or "Re-authorization required" in error_msg:
                    return Response({
                        'error': 'Main calendar authentication required',
                        'details': f'Calendar "{main_calendar.name}" needs re-authorization: {error_msg}',
                        'config_name': config.name,
                        'requires_reauth': True
                    }, status=status.HTTP_401_UNAUTHORIZED)
                else:
                    raise  # Re-raise other ValueError types
            
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
                'config_name': config.name,
                'calendar_health': calendar_health
            }
            
            # Add warnings if some conflict calendars failed during availability check
            if calendar_health['failed_calendars']:
                response_data['warnings'] = [
                    f"Appointment booked successfully, but {len(calendar_health['failed_calendars'])} conflict calendars could not be checked: {', '.join(calendar_health['failed_calendars'])}"
                ]
            
            logger.info(f"✅ Successfully booked appointment for config {config.id}: {title} at {start_time}")
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"❌ Error booking appointment for config {config.id}: {str(e)}")
            
            # Provide detailed error response
            error_response = {
                'error': 'Failed to book appointment',
                'details': str(e),
                'config_name': config.name,
                'start_time': start_time.isoformat() if start_time else None,
                'title': title
            }
            
            return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
        """Get busy times from all conflict_check_calendars with robust error handling"""
        busy_times = []
        
        start_datetime = datetime.combine(date, config.from_time)
        end_datetime = datetime.combine(date, config.to_time)
        
        # Make timezone aware
        start_datetime = timezone.make_aware(start_datetime)
        end_datetime = timezone.make_aware(end_datetime)
        
        failed_calendars = []
        
        for calendar_id in config.conflict_check_calendars:
            try:
                conflict_calendar = Calendar.objects.select_related(
                    'google_calendar__connection', 'microsoft_calendar__connection'
                ).get(id=calendar_id)
                
                # Ensure provider-specific data is present
                if conflict_calendar.provider == 'google' and not hasattr(conflict_calendar, 'google_calendar'):
                    logger.warning(f"Calendar {calendar_id} missing google_calendar data")
                    failed_calendars.append(conflict_calendar.name if hasattr(conflict_calendar, 'name') else str(calendar_id))
                    continue
                if conflict_calendar.provider == 'outlook' and not hasattr(conflict_calendar, 'microsoft_calendar'):
                    logger.warning(f"Calendar {calendar_id} missing microsoft_calendar data")
                    failed_calendars.append(conflict_calendar.name if hasattr(conflict_calendar, 'name') else str(calendar_id))
                    continue

                # Check tokens via provider
                if conflict_calendar.provider == 'google':
                    conn = conflict_calendar.google_calendar.connection
                else:
                    conn = conflict_calendar.microsoft_calendar.connection
                if not conn or not getattr(conn, 'access_token', None):
                    logger.warning(f"Calendar {conflict_calendar.name} has no valid tokens - skipping availability check")
                    failed_calendars.append(conflict_calendar.name)
                    continue

                # Use provider-agnostic factory
                service = CalendarServiceFactory.get_service(conflict_calendar)
                external_id = (
                    conflict_calendar.google_calendar.external_id
                    if conflict_calendar.provider == 'google' else
                    conflict_calendar.microsoft_calendar.external_id
                )
                
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
                failed_calendars.append(str(calendar_id))
                continue
            except ValueError as e:
                # Handle OAuth/token errors gracefully
                error_msg = str(e)
                if "Missing tokens" in error_msg or "Re-authorization required" in error_msg:
                    logger.warning(f"Calendar {calendar_id} needs re-authorization - skipping for availability check: {error_msg}")
                    failed_calendars.append(conflict_calendar.name if 'conflict_calendar' in locals() else str(calendar_id))
                else:
                    logger.error(f"OAuth error for calendar {calendar_id}: {error_msg}")
                    failed_calendars.append(conflict_calendar.name if 'conflict_calendar' in locals() else str(calendar_id))
                continue
            except Exception as e:
                logger.error(f"Unexpected error getting busy times for calendar {calendar_id}: {str(e)}")
                failed_calendars.append(conflict_calendar.name if 'conflict_calendar' in locals() else str(calendar_id))
                continue
        
        # Log summary of failed calendars for monitoring
        if failed_calendars:
            logger.warning(f"Failed to check availability for {len(failed_calendars)} calendars: {', '.join(failed_calendars)}")
        
        return busy_times
    
    def _get_busy_times_from_conflicts_with_health(self, config: CalendarConfiguration, date) -> dict:
        """Get busy times with comprehensive health status tracking"""
        busy_times = []
        failed_calendars = []
        token_issues = []
        successful_calendars = []
        
        start_datetime = datetime.combine(date, config.from_time)
        end_datetime = datetime.combine(date, config.to_time)
        
        # Make timezone aware
        start_datetime = timezone.make_aware(start_datetime)
        end_datetime = timezone.make_aware(end_datetime)
        
        total_calendars = len(config.conflict_check_calendars)
        
        for calendar_id in config.conflict_check_calendars:
            calendar_name = f"Calendar-{calendar_id}"
            
            try:
                conflict_calendar = Calendar.objects.select_related(
                    'google_calendar__connection', 'microsoft_calendar__connection'
                ).get(id=calendar_id)
                
                calendar_name = conflict_calendar.name
                
                # Ensure provider-specific data exists
                if conflict_calendar.provider == 'google' and not hasattr(conflict_calendar, 'google_calendar'):
                    logger.warning(f"Calendar {calendar_name} has no google_calendar data")
                    failed_calendars.append(calendar_name)
                    continue
                if conflict_calendar.provider == 'outlook' and not hasattr(conflict_calendar, 'microsoft_calendar'):
                    logger.warning(f"Calendar {calendar_name} has no microsoft_calendar data")
                    failed_calendars.append(calendar_name)
                    continue

                # Check tokens
                if conflict_calendar.provider == 'google':
                    conn = conflict_calendar.google_calendar.connection
                else:
                    conn = conflict_calendar.microsoft_calendar.connection
                if not conn or not getattr(conn, 'access_token', None):
                    logger.warning(f"Calendar {calendar_name} has no valid tokens - skipping availability check")
                    token_issues.append(calendar_name)
                    continue

                # Use provider-agnostic factory
                service = CalendarServiceFactory.get_service(conflict_calendar)
                external_id = (
                    conflict_calendar.google_calendar.external_id
                    if conflict_calendar.provider == 'google' else
                    conflict_calendar.microsoft_calendar.external_id
                )
                
                # Get busy times for this calendar
                calendar_busy = service.check_availability(external_id, start_datetime, end_datetime)
                
                # Format busy times
                for busy_period in calendar_busy:
                    busy_times.append({
                        'start': busy_period.get('start'),
                        'end': busy_period.get('end'),
                        'calendar_name': calendar_name
                    })
                
                successful_calendars.append(calendar_name)
                logger.debug(f"Successfully checked availability for {calendar_name}: {len(calendar_busy)} busy periods")
                    
            except Calendar.DoesNotExist:
                logger.warning(f"Conflict calendar {calendar_id} not found")
                failed_calendars.append(calendar_name)
                continue
            except ValueError as e:
                # Handle OAuth/token errors gracefully
                error_msg = str(e)
                if "Missing tokens" in error_msg or "Re-authorization required" in error_msg:
                    logger.warning(f"Calendar {calendar_name} needs re-authorization - skipping for availability check: {error_msg}")
                    token_issues.append(calendar_name)
                else:
                    logger.error(f"OAuth error for calendar {calendar_name}: {error_msg}")
                    failed_calendars.append(calendar_name)
                continue
            except Exception as e:
                logger.error(f"Unexpected error getting busy times for calendar {calendar_name}: {str(e)}")
                failed_calendars.append(calendar_name)
                continue
        
        # Determine overall health status
        if len(successful_calendars) == total_calendars:
            health_status = 'healthy'
        elif len(successful_calendars) > 0:
            health_status = 'partial'
        else:
            health_status = 'unhealthy'
        
        # Create comprehensive health report
        health_info = {
            'status': health_status,
            'total_calendars': total_calendars,
            'successful_calendars': len(successful_calendars),
            'failed_calendars': failed_calendars,
            'token_issues': token_issues,
            'message': self._get_health_message(health_status, total_calendars, len(successful_calendars), token_issues, failed_calendars)
        }
        
        logger.info(f"Calendar health check for config {config.id}: {health_status} - {len(successful_calendars)}/{total_calendars} calendars successful")
        
        return {
            'busy_times': busy_times,
            'health_status': health_info
        }
    
    def _get_health_message(self, status: str, total: int, successful: int, token_issues: list, failed: list) -> str:
        """Generate human-readable health status message"""
        if status == 'healthy':
            return f"All {total} calendars checked successfully"
        elif status == 'partial':
            issues = []
            if token_issues:
                issues.append(f"{len(token_issues)} need re-authorization")
            if failed:
                issues.append(f"{len(failed)} had other issues")
            return f"{successful}/{total} calendars checked successfully. {', '.join(issues)}"
        else:
            return f"Could not check any calendars. {len(token_issues)} need re-authorization, {len(failed)} had other issues"
    
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
            
            # Make timezone aware (do this before checking conflicts)
            slot_start_aware = timezone.make_aware(slot_start)
            slot_end_aware = timezone.make_aware(slot_end)
            
            # Check if slot conflicts with busy times
            is_available = True
            
            for busy_period in busy_times:
                busy_start = busy_period.get('start')
                busy_end = busy_period.get('end')
                
                # Handle string datetime conversion more robustly
                try:
                    if isinstance(busy_start, str):
                        busy_start = datetime.fromisoformat(busy_start.replace('Z', '+00:00'))
                    if isinstance(busy_end, str):
                        busy_end = datetime.fromisoformat(busy_end.replace('Z', '+00:00'))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse busy time: {e}")
                    continue
                
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
        """Build generic event data from config (usable by provider services)"""
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Base event data (generic shape)
        event_data = {
            'summary': title,
            'start': start_time.isoformat(),
            'end': end_time.isoformat(),
            'attendees': [{'email': attendee_email, 'name': attendee_name or attendee_email, 'type': 'required'}]
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


## Google Calendar MCP token management removed in unified LiveKit-only flow