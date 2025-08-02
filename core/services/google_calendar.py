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
    
    def __init__(self, connection: GoogleCalendarConnection):
        self.connection = connection
        
    def _make_timezone_aware(self, dt):
        """Convert timezone-naive datetime to timezone-aware UTC datetime"""
        if dt is None:
            return None
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt
        
    def get_credentials(self) -> Credentials:
        """Get refreshed Google credentials"""
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
                credentials.refresh(Request())
                self._update_connection_tokens(credentials)
                logger.info(f"Refreshed tokens for {self.connection.account_email}")
            except Exception as e:
                logger.error(f"Failed to refresh token for {self.connection.account_email}: {str(e)}")
                raise
                
        return credentials
    
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
            logger.error(f"Connection test failed for {self.connection.account_email}: {str(e)}")
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
            
            logger.info(f"Synced {len(synced_calendars)} calendars for {self.connection.account_email}")
            return synced_calendars
            
        except Exception as e:
            error_msg = f"Failed to sync calendars: {str(e)}"
            logger.error(f"Calendar sync failed for {self.connection.account_email}: {error_msg}")
            
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
            # Create or get the generic Calendar
            calendar, created = Calendar.objects.get_or_create(
                workspace=self.connection.workspace,
                name=calendar_data['summary'],
                provider='google',
                defaults={'active': True}
            )
            
            # Create or update GoogleCalendar using only existing fields
            google_calendar, gc_created = GoogleCalendar.objects.update_or_create(
                external_id=calendar_data['id'],
                defaults={
                    'calendar': calendar,
                    'primary': calendar_data.get('primary', False),
                    'time_zone': calendar_data.get('timeZone', 'UTC'),
                    # Note: We don't store tokens here anymore as they're in GoogleCalendarConnection
                    'refresh_token': '',  # Keep empty - tokens are in connection
                    'access_token': '',   # Keep empty - tokens are in connection
                    'token_expires_at': timezone.now(),  # Placeholder
                    'scopes': []  # Keep empty - scopes are in connection
                }
            )
            
            if created or gc_created:
                logger.info(f"{'Created' if created else 'Updated'} calendar: {calendar_data['summary']}")
            
            return calendar
            
        except Exception as e:
            logger.error(f"Failed to create/update calendar {calendar_data.get('summary', 'Unknown')}: {str(e)}")
            return None
    
    def check_availability(self, calendar_id: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Check availability using Google Free/Busy API"""
        try:
            service = self.get_service()
            
            body = {
                'timeMin': start_time.isoformat(),
                'timeMax': end_time.isoformat(),
                'items': [{'id': calendar_id}]
            }
            
            freebusy_result = service.freebusy().query(body=body).execute()
            busy_times = freebusy_result.get('calendars', {}).get(calendar_id, {}).get('busy', [])
            
            return busy_times
            
        except HttpError as e:
            logger.error(f"Google API error checking availability: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to check availability for calendar {calendar_id}: {str(e)}")
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
            
            if google_calendar.access_role not in ['writer', 'owner']:
                raise ValueError(f"Cannot create events in calendar with {google_calendar.access_role} access")
            
            event = service.events().insert(
                calendarId=calendar_id,
                body=event_data
            ).execute()
            
            logger.info(f"Created event {event['id']} in calendar {calendar_id}")
            return event
            
        except HttpError as e:
            logger.error(f"Google API error creating event: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to create event in calendar {calendar_id}: {str(e)}")
            raise


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
            return GoogleCalendarService(calendar.google_calendar.connection)
        else:
            raise ValueError(f"Unsupported calendar provider: {calendar.provider}") 