"""
Google Calendar API service for handling OAuth and calendar operations.
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Dict, List, Optional, Tuple
from django.conf import settings
from django.utils import timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests

from core.models import GoogleCalendarConnection, GoogleCalendar, Calendar

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Service for Google Calendar API interactions"""
    
    def __init__(self, google_calendar_or_connection):
        # Support multiple initialization modes for backward compatibility
        if hasattr(google_calendar_or_connection, 'workspace') and hasattr(google_calendar_or_connection, 'account_email'):
            # This is a GoogleCalendarConnection object (new preferred way)
            self.connection = google_calendar_or_connection
            self.google_calendar = None
        elif hasattr(google_calendar_or_connection, 'connection'):
            # This is a GoogleCalendar object with connection reference (new way)
            self.google_calendar = google_calendar_or_connection
            self.connection = google_calendar_or_connection.connection
        elif hasattr(google_calendar_or_connection, 'refresh_token'):
            # This is a GoogleCalendar object with direct token fields (legacy mode)
            self.google_calendar = google_calendar_or_connection
            self.connection = google_calendar_or_connection  # Use same object as connection for compatibility
        else:
            raise ValueError("Invalid input: Expected GoogleCalendarConnection or GoogleCalendar object")
    
    def get_account_email(self):
        """Get account email for logging - compatible with both object types"""
        if self.google_calendar and hasattr(self.google_calendar, 'calendar'):
            return self.google_calendar.calendar.name  # Calendar name is usually the email
        elif hasattr(self.connection, 'account_email'):
            return self.connection.account_email
        else:
            return "unknown@email.com"
        
    def _make_timezone_aware(self, dt):
        """Convert timezone-naive datetime to timezone-aware UTC datetime"""
        if dt is None:
            return None
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt
        
    def get_credentials(self) -> Credentials:
        """Get refreshed Google credentials with robust error handling and graceful degradation"""
        
        # Check if we have basic tokens first
        if not self.connection.access_token or not self.connection.refresh_token:
            error_msg = f"Missing tokens for {self.get_account_email()}. Re-authorization required."
            logger.error(f"🚨 TOKEN MISSING: {error_msg}")
            
            # Mark connection as needing reauth for monitoring
            self._mark_connection_needs_reauth("missing_tokens")
            raise ValueError(error_msg)
        
        credentials = Credentials(
            token=self.connection.access_token,
            refresh_token=self.connection.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=self.connection.scopes
        )
        
        # Check if token needs refresh
        if credentials.expired or self._token_expires_soon():
            try:
                logger.info(f"🔄 REFRESHING TOKEN: {self.get_account_email()} (expires: {self.connection.token_expires_at})")
                credentials.refresh(Request())
                self._update_connection_tokens(credentials)
                
                # Clear any previous error status
                self._clear_connection_error_status()
                logger.info(f"✅ TOKEN REFRESH SUCCESS: {self.get_account_email()}")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ TOKEN REFRESH FAILED: {self.get_account_email()} - {error_msg}")
                
                # Check for specific Google API errors that require re-authorization
                if self._is_reauth_required_error(error_msg):
                    logger.error(f"🚨 REAUTH REQUIRED: {self.get_account_email()}")
                    
                    # Clear invalid tokens and mark for reauth
                    self._clear_invalid_tokens()
                    self._mark_connection_needs_reauth("invalid_grant")
                    
                    raise ValueError(f"Re-authorization required for {self.get_account_email()}. Please reconnect your Google Calendar.")
                else:
                    # Other types of errors (network, temporary, etc.)
                    self._mark_connection_error("refresh_failed", error_msg)
                    raise RuntimeError(f"Token refresh failed for {self.get_account_email()}: {error_msg}")
                
        return credentials
    
    def _mark_connection_needs_reauth(self, reason: str):
        """Mark connection as needing re-authorization for monitoring"""
        try:
            if not hasattr(self.connection, 'auth_status'):
                # If the field doesn't exist, we'll skip this for now
                logger.warning(f"Connection {self.get_account_email()} doesn't have auth_status field")
                return
                
            self.connection.auth_status = 'needs_reauth'
            self.connection.last_error = {
                'type': 'auth_required',
                'reason': reason,
                'timestamp': timezone.now().isoformat()
            }
            self.connection.save(update_fields=['auth_status', 'last_error', 'updated_at'])
            logger.info(f"Marked {self.get_account_email()} as needing re-authorization")
        except Exception as e:
            logger.warning(f"Failed to mark connection status for {self.get_account_email()}: {str(e)}")
    
    def _mark_connection_error(self, error_type: str, error_msg: str):
        """Mark connection as having an error for monitoring"""
        try:
            if hasattr(self.connection, 'last_error'):
                self.connection.last_error = {
                    'type': error_type,
                    'message': error_msg,
                    'timestamp': timezone.now().isoformat()
                }
                self.connection.save(update_fields=['last_error', 'updated_at'])
        except Exception as e:
            logger.warning(f"Failed to mark connection error for {self.get_account_email()}: {str(e)}")
    
    def _clear_connection_error_status(self):
        """Clear error status when connection is working again"""
        try:
            if hasattr(self.connection, 'auth_status') and self.connection.auth_status == 'needs_reauth':
                self.connection.auth_status = 'active'
            if hasattr(self.connection, 'last_error'):
                self.connection.last_error = None
            self.connection.save(update_fields=['auth_status', 'last_error', 'updated_at'])
        except Exception as e:
            logger.warning(f"Failed to clear connection status for {self.get_account_email()}: {str(e)}")
    
    def _is_reauth_required_error(self, error_msg: str) -> bool:
        """Check if the error indicates re-authorization is required"""
        reauth_keywords = [
            'invalid_grant',
            'refresh_token',
            'authorization_revoked',
            'invalid_client',
            'unauthorized_client',
            'access_denied',
            'token_expired',
            'invalid_token'
        ]
        
        error_lower = error_msg.lower()
        return any(keyword in error_lower for keyword in reauth_keywords)
    
    def _clear_invalid_tokens(self):
        """Clear invalid tokens from the database"""
        try:
            self.connection.access_token = None
            self.connection.refresh_token = None
            self.connection.save(update_fields=['access_token', 'refresh_token', 'updated_at'])
            logger.info(f"Cleared invalid tokens for {self.get_account_email()}")
        except Exception as e:
            logger.error(f"Failed to clear tokens for {self.get_account_email()}: {str(e)}")
    
    def _token_expires_soon(self, minutes=5) -> bool:
        """Check if token expires in the next X minutes"""
        if not self.connection.token_expires_at:
            return True
        # Ensure both datetimes are timezone-aware for comparison
        token_expiry = self._make_timezone_aware(self.connection.token_expires_at)
        return token_expiry <= timezone.now() + timedelta(minutes=minutes)
    
    def _update_connection_tokens(self, credentials: Credentials):
        """Update connection with new tokens"""
        self.connection.access_token = credentials.token
        # Convert expiry to timezone-aware datetime
        self.connection.token_expires_at = self._make_timezone_aware(credentials.expiry)
        self.connection.save(update_fields=['access_token', 'token_expires_at', 'updated_at'])
    
    def get_service(self):
        """Get authenticated Google Calendar service"""
        credentials = self.get_credentials()
        return build('calendar', 'v3', credentials=credentials)
    
    def test_connection(self) -> Dict:
        """Test the Google Calendar connection"""
        try:
            service = self.get_service()
            calendar_list = service.calendarList().list(maxResults=1).execute()
            return {
                'success': True,
                'message': 'Connection successful',
                'calendars_available': len(calendar_list.get('items', []))
            }
        except Exception as e:
            logger.error(f"Connection test failed for {self.get_account_email()}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def sync_calendars(self) -> List[Calendar]:
        """Sync calendar list from Google and create/update local records"""
        try:
            service = self.get_service()
            calendar_list = service.calendarList().list().execute()
            
            synced_calendars = []
            for item in calendar_list.get('items', []):
                calendar = self._create_or_update_calendar(item)
                if calendar:
                    synced_calendars.append(calendar)
            
            # Update last sync time
            self.connection.last_sync = timezone.now()
            self.connection.sync_errors = {}
            self.connection.save(update_fields=['last_sync', 'sync_errors', 'updated_at'])
            
            logger.info(f"Synced {len(synced_calendars)} calendars for {self.get_account_email()}")
            return synced_calendars
            
        except Exception as e:
            error_msg = f"Failed to sync calendars: {str(e)}"
            logger.error(f"Calendar sync failed for {self.get_account_email()}: {error_msg}")
            
            # Store sync error
            self.connection.sync_errors = {
                'last_error': error_msg,
                'timestamp': timezone.now().isoformat()
            }
            self.connection.save(update_fields=['sync_errors', 'updated_at'])
            raise
    
    def _create_or_update_calendar(self, calendar_data: Dict) -> Optional[Calendar]:
        """Create or update a calendar from Google API data"""
        try:
            # Create or update the generic Calendar - always set active=True on sync
            calendar, created = Calendar.objects.update_or_create(
                workspace=self.connection.workspace,
                name=calendar_data['summary'],
                provider='google',
                defaults={'active': True}
            )
            
            # Create or update GoogleCalendar with connection reference
            google_calendar, gc_created = GoogleCalendar.objects.update_or_create(
                external_id=calendar_data['id'],
                defaults={
                    'calendar': calendar,
                    'connection': self.connection,  # Link to GoogleCalendarConnection
                    'primary': calendar_data.get('primary', False),
                    'time_zone': calendar_data.get('timeZone', 'UTC'),
                    'access_role': calendar_data.get('accessRole', 'reader'),  # Add access_role from Google API
                    # Legacy fields - kept empty as tokens come from connection
                    'refresh_token': '',  # DEPRECATED: Use connection.refresh_token
                    'access_token': '',   # DEPRECATED: Use connection.access_token
                    'token_expires_at': None,  # DEPRECATED: Use connection.token_expires_at
                    'scopes': []  # DEPRECATED: Use connection.scopes
                }
            )
            
            if created or gc_created:
                logger.info(f"{'Created' if created else 'Updated'} calendar: {calendar_data['summary']} (access: {calendar_data.get('accessRole', 'reader')})")
            
            return calendar
            
        except Exception as e:
            logger.error(f"Failed to create/update calendar {calendar_data.get('summary', 'Unknown')}: {str(e)}")
            return None
    
    def check_availability(self, calendar_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Check availability using Google Free/Busy API with robust error handling"""
        try:
            service = self.get_service()
            
            body = {
                'timeMin': start_time.isoformat(),
                'timeMax': end_time.isoformat(),
                'items': [{'id': calendar_id}]
            }
            
            logger.debug(f"Checking availability for calendar {calendar_id} from {start_time} to {end_time}")
            freebusy_result = service.freebusy().query(body=body).execute()
            busy_times = freebusy_result.get('calendars', {}).get(calendar_id, {}).get('busy', [])
            
            logger.debug(f"Found {len(busy_times)} busy periods for calendar {calendar_id}")
            return busy_times
            
        except ValueError as e:
            # Handle OAuth/token errors - these are expected and should be handled gracefully
            error_msg = str(e)
            if "Missing tokens" in error_msg or "Re-authorization required" in error_msg:
                logger.warning(f"Calendar {calendar_id} needs re-authorization: {error_msg}")
                # Return empty busy times rather than failing - graceful degradation
                return []
            else:
                logger.error(f"OAuth error checking availability for calendar {calendar_id}: {error_msg}")
                raise
                
        except HttpError as e:
            status_code = e.resp.status
            logger.error(f"Google API error checking availability (HTTP {status_code}): {str(e)}")
            
            # Handle specific HTTP errors gracefully
            if status_code == 401:
                logger.warning(f"Unauthorized access to calendar {calendar_id} - tokens may need refresh")
                return []  # Graceful degradation
            elif status_code == 403:
                logger.warning(f"Forbidden access to calendar {calendar_id} - insufficient permissions")
                return []  # Graceful degradation
            elif status_code == 404:
                logger.warning(f"Calendar {calendar_id} not found")
                return []  # Graceful degradation
            elif status_code >= 500:
                logger.error(f"Google API server error for calendar {calendar_id}")
                raise  # Server errors should be retried
            else:
                raise  # Other errors should be handled by caller
                
        except Exception as e:
            logger.error(f"Unexpected error checking availability for calendar {calendar_id}: {str(e)}")
            raise
    
    def create_event(self, calendar_id: str, event_data: Dict) -> Dict:
        """Create an event in Google Calendar"""
        try:
            service = self.get_service()
            
            # Check if calendar allows event creation
            google_calendar = GoogleCalendar.objects.get(
                connection=self.connection,
                external_id=calendar_id
            )
            
            # Check calendar permissions if access_role is available
            access_role = getattr(google_calendar, 'access_role', 'reader')
            if access_role not in ['writer', 'owner']:
                logger.warning(f"Calendar {calendar_id} has {access_role} access - may not be able to create events")
                # Continue anyway - let Google API return appropriate error if needed
            
            # Map generic fields to Google payload
            body = {
                'summary': event_data.get('summary') or event_data.get('subject', ''),
                'description': event_data.get('description') or event_data.get('body', ''),
                'start': { 'dateTime': event_data.get('start') },
                'end': { 'dateTime': event_data.get('end') },
                'attendees': [{'email': a.get('email'), 'displayName': a.get('name')} for a in event_data.get('attendees', [])]
            }
            if event_data.get('location'):
                body['location'] = event_data.get('location')

            # Automatically create Google Meet link if requested
            if event_data.get('create_meet'):
                body['conferenceData'] = {
                    'createRequest': {
                        'requestId': f"hotcalls-{int(timezone.now().timestamp())}",
                        'conferenceSolutionKey': { 'type': 'hangoutsMeet' },
                    }
                }

            event = service.events().insert(
                calendarId=calendar_id,
                body=body,
                conferenceDataVersion=1 if event_data.get('create_meet') else 0
            ).execute()
            
            logger.info(f"Created event {event['id']} in calendar {calendar_id}")
            return event
            
        except HttpError as e:
            logger.error(f"Google API error creating event: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to create event in calendar {calendar_id}: {str(e)}")
            raise

    # -----------------------------
    # Reconciliation helpers
    # -----------------------------
    @staticmethod
    def ensure_calendar_mapping(calendar: Calendar) -> bool:
        """Ensure that a provider-mapped record exists for the given calendar.

        For Google:
        - If mapping exists, ensure it has a connection and return True
        - If missing, try to attach mapping by syncing the workspace connection
          and re-linking by exact name match
        - Returns True if mapping now exists; False otherwise
        """
        try:
            if calendar.provider != 'google':
                return True

            # Mapping already present
            if hasattr(calendar, 'google_calendar') and calendar.google_calendar:
                # Ensure connection attached if available in workspace
                if not calendar.google_calendar.connection:
                    from core.models import GoogleCalendarConnection
                    conn = GoogleCalendarConnection.objects.filter(
                        workspace=calendar.workspace, active=True
                    ).first()
                    if not conn:
                        return False
                    calendar.google_calendar.connection = conn
                    calendar.google_calendar.save(update_fields=['connection', 'updated_at'])
                return True

            # No mapping yet: try to reconcile via workspace connection
            from core.models import GoogleCalendarConnection, GoogleCalendar
            conn = GoogleCalendarConnection.objects.filter(
                workspace=calendar.workspace, active=True
            ).first()
            if not conn:
                return False

            # Sync to ensure latest list exists in DB
            try:
                GoogleCalendarService(conn).sync_calendars()
            except Exception as e:
                logger.warning(f"Sync during ensure_calendar_mapping failed: {e}")

            # Find a GoogleCalendar created by sync with the same name in this workspace/connection
            gc = (
                GoogleCalendar.objects.filter(
                    connection=conn,
                    calendar__workspace=calendar.workspace,
                    calendar__name=calendar.name
                ).first()
            )
            if gc:
                # Re-link mapping to the existing orphan calendar
                old_calendar = gc.calendar
                if old_calendar.id != calendar.id:
                    gc.calendar = calendar
                    gc.save(update_fields=['calendar', 'updated_at'])
                return True

            return False
        except Exception as e:
            logger.error(f"ensure_calendar_mapping error for calendar {getattr(calendar, 'id', 'unknown')}: {e}")
            return False

    @staticmethod
    def reconcile_workspace_calendars(connection: 'GoogleCalendarConnection') -> int:
        """Reconcile all Google calendars in a workspace to prevent orphans.

        Steps:
        - Run a full sync to populate GoogleCalendar entries
        - For each generic Calendar(provider='google') without mapping, attempt to link
        Returns the number of calendars successfully fixed.
        """
        try:
            service = GoogleCalendarService(connection)
            # Ensure we have an up-to-date set of calendars
            try:
                service.sync_calendars()
            except Exception as e:
                logger.warning(f"Initial sync failed during reconcile: {e}")

            from core.models import Calendar
            orphans = Calendar.objects.filter(
                workspace=connection.workspace,
                provider='google',
                google_calendar__isnull=True
            )

            fixed = 0
            for orphan in orphans:
                if GoogleCalendarService.ensure_calendar_mapping(orphan):
                    fixed += 1
            if fixed:
                logger.info(f"Reconciled {fixed} Google calendar mappings in workspace {connection.workspace_id}")
            return fixed
        except Exception as e:
            logger.error(f"reconcile_workspace_calendars failed: {e}")
            return 0


class GoogleOAuthService:
    """Service for Google OAuth operations"""
    
    @staticmethod
    def get_authorization_url(state: str = None) -> str:
        """Generate Google OAuth authorization URL"""
        from google_auth_oauthlib.flow import Flow
        
        try:
            flow = Flow.from_client_config(
                client_config={
                    "web": {
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                },
                scopes=settings.GOOGLE_SCOPES
            )
            flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
            
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent',
                state=state,
                include_granted_scopes='true'
            )
            
            return authorization_url
            
        except Exception as e:
            logger.error(f"Failed to generate authorization URL: {str(e)}")
            raise
    
    @staticmethod
    def exchange_code_for_tokens(code: str) -> Credentials:
        """Exchange authorization code for access and refresh tokens"""
        try:
            flow = Flow.from_client_config(
                client_config={
                    "web": {
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                },
                scopes=settings.GOOGLE_SCOPES
            )
            flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
            flow.fetch_token(code=code)
            
            return flow.credentials
            
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {str(e)}")
            raise
    
    @staticmethod
    def get_user_info(credentials: Credentials) -> Dict:
        """Get user info from Google using credentials"""
        try:
            # Use the people API to get user info
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            
            return {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
                'verified_email': user_info.get('verified_email', False)
            }
            
        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            raise
    
    @staticmethod
    def revoke_token(refresh_token: str) -> bool:
        """Revoke a Google refresh token"""
        try:
            response = requests.post(
                'https://oauth2.googleapis.com/revoke',
                params={'token': refresh_token},
                headers={'content-type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                logger.info("Successfully revoked Google token")
                return True
            else:
                logger.warning(f"Token revocation returned status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to revoke token: {str(e)}")
            return False


class CalendarServiceFactory:
    """Factory for creating calendar services"""
    
    @staticmethod
    def get_service(calendar: Calendar):
        """Get appropriate calendar service based on provider"""
        if calendar.provider == 'google':
            if not hasattr(calendar, 'google_calendar'):
                raise ValueError(f"Google calendar data not found for calendar {calendar.id}")
            return GoogleCalendarService(calendar.google_calendar)
        elif calendar.provider == 'outlook':
            # Lazy import to avoid circular dependencies if MS service is created later
            from core.services.microsoft_calendar import MicrosoftCalendarService  # type: ignore
            if not hasattr(calendar, 'microsoft_calendar'):
                raise ValueError(f"Microsoft calendar data not found for calendar {calendar.id}")
            return MicrosoftCalendarService(calendar.microsoft_calendar)
        else:
            raise ValueError(f"Unsupported calendar provider: {calendar.provider}") 