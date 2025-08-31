"""
Google Calendar API service for handling OAuth and calendar operations.
"""
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Dict, List
from django.conf import settings
from django.utils import timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError  # noqa: F401
import requests

from core.models import GoogleCalendar

logger = logging.getLogger(__name__)


class GoogleOAuthService:
    """Service for Google OAuth operations"""
    
    @staticmethod
    def get_authorization_url(state: str = None) -> str:
        """Generate Google OAuth authorization URL"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=settings.GOOGLE_SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state
        )
        
        return authorization_url
    
    @staticmethod
    def exchange_code_for_tokens(code: str) -> Dict:
        """Exchange authorization code for access and refresh tokens"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=settings.GOOGLE_SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Calculate expires_in with proper timezone handling
        if credentials.expiry:
            # Ensure expiry is timezone-aware
            if credentials.expiry.tzinfo is None:
                # If naive, assume UTC
                expiry_aware = credentials.expiry.replace(tzinfo=dt_timezone.utc)
            else:
                expiry_aware = credentials.expiry
            expires_in = (expiry_aware - datetime.now(dt_timezone.utc)).total_seconds()
        else:
            expires_in = 3600
            
        return {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_in': expires_in,
            'scope': ' '.join(credentials.scopes) if credentials.scopes else ''
        }


class GoogleCalendarService:
    """Service for Google Calendar API interactions"""
    
    def __init__(self, google_calendar=None):
        """Initialize with optional GoogleCalendar model"""
        self.google_calendar = google_calendar
    
    @staticmethod
    def get_authorization_url(state: str = None) -> str:
        """Generate Google OAuth authorization URL"""
        return GoogleOAuthService.get_authorization_url(state)
    
    @staticmethod
    def exchange_code_for_tokens(code: str) -> Dict:
        """Exchange authorization code for tokens"""
        return GoogleOAuthService.exchange_code_for_tokens(code)
    
    @staticmethod
    def get_user_info(access_token: str) -> Dict:
        """Get user info from Google"""
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get('https://www.googleapis.com/oauth2/v1/userinfo', headers=headers)
        response.raise_for_status()
        return response.json()
    
    def get_credentials(self) -> Credentials:
        """Get or refresh Google OAuth credentials"""
        if not self.google_calendar:
            raise ValueError("No GoogleCalendar object available")
            
        if not self.google_calendar.refresh_token:
            raise ValueError("No refresh token available")
        
        credentials = Credentials(
            token=self.google_calendar.access_token,
            refresh_token=self.google_calendar.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=self.google_calendar.scopes or settings.GOOGLE_SCOPES
        )
        
        # Set expiry if available (google-auth compares with naive utcnow → use naive-UTC)
        if self.google_calendar.token_expires_at:
            exp = self.google_calendar.token_expires_at
            try:
                if exp.tzinfo is None:
                    # already naive → assume UTC
                    exp_naive = exp
                else:
                    exp_naive = exp.astimezone(dt_timezone.utc).replace(tzinfo=None)
            except Exception:
                exp_naive = exp
            credentials.expiry = exp_naive
        
        # Refresh if needed; be defensive against naive/aware comparisons in google-auth
        try:
            needs_refresh = not credentials.valid
        except Exception:
            needs_refresh = True
        if needs_refresh and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._update_tokens(credentials)
            except Exception as e:
                logger.error(f"Failed to refresh token: {str(e)}")
                raise
        
        return credentials
    
    def _update_tokens(self, credentials: Credentials):
        """Update tokens in the database"""
        self.google_calendar.access_token = credentials.token
        if credentials.expiry:
            self.google_calendar.token_expires_at = credentials.expiry
        if credentials.refresh_token:
            self.google_calendar.refresh_token = credentials.refresh_token
        self.google_calendar.save(update_fields=['access_token', 'token_expires_at', 'refresh_token', 'updated_at'])
    
    def get_service(self):
        """Get authenticated Google Calendar service"""
        credentials = self.get_credentials()
        return build('calendar', 'v3', credentials=credentials)
    
    def sync_calendars(self, google_calendar: GoogleCalendar) -> List[Dict]:
        """
        Sync calendars from Google using sub-accounts.
        Returns list of synced calendar data for each active sub-account.
        """
        synced_calendars = []
        errors = {}
        
        try:
            # Get credentials for the main account
            # Use configured OAuth client, not undefined instance attributes
            credentials = Credentials(
                token=google_calendar.access_token,
                refresh_token=google_calendar.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=google_calendar.scopes or settings.GOOGLE_SCOPES
            )
            
            service = build('calendar', 'v3', credentials=credentials)
            
            # Iterate through active sub-accounts
            for sub_account in google_calendar.sub_accounts.filter(active=True):
                try:
                    # For 'self' relationship, use primary calendar
                    if sub_account.relationship == 'self':
                        calendar_id = 'primary'
                    else:
                        calendar_id = sub_account.act_as_email
                    
                    # Get calendar details
                    calendar = service.calendars().get(calendarId=calendar_id).execute()
                    
                    # Get calendar settings (for more details)
                    calendar_list_entry = service.calendarList().get(calendarId=calendar_id).execute()
                    
                    synced_data = {
                        'sub_account_id': str(sub_account.id),
                        'calendar_id': calendar_id,
                        'act_as_email': sub_account.act_as_email,
                        'relationship': sub_account.relationship,
                        'summary': calendar.get('summary', ''),
                        'description': calendar.get('description', ''),
                        'time_zone': calendar.get('timeZone', 'UTC'),
                        'access_role': calendar_list_entry.get('accessRole', 'reader'),
                        'background_color': calendar_list_entry.get('backgroundColor', ''),
                        'foreground_color': calendar_list_entry.get('foregroundColor', ''),
                        'selected': calendar_list_entry.get('selected', False),
                        'primary': calendar_list_entry.get('primary', False),
                    }
                    
                    synced_calendars.append(synced_data)
                    logger.info(f"Synced calendar for sub-account: {sub_account.act_as_email}")
                    
                except Exception as e:
                    error_msg = f"Failed to sync {sub_account.act_as_email}: {str(e)}"
                    errors[sub_account.act_as_email] = error_msg
                    logger.error(error_msg)
            
            # Update sync status
            google_calendar.last_sync = timezone.now()
            google_calendar.sync_errors = errors if errors else {}
            google_calendar.save()
            
        except Exception as e:
            logger.error(f"Failed to sync Google calendars: {str(e)}")
            google_calendar.sync_errors = {'error': str(e), 'timestamp': timezone.now().isoformat()}
            google_calendar.save()
            
        return synced_calendars
    
    def revoke_tokens(self, google_calendar: GoogleCalendar):
        """Revoke Google OAuth tokens"""
        if google_calendar.access_token:
            try:
                requests.post(
                    'https://oauth2.googleapis.com/revoke',
                    params={'token': google_calendar.access_token},
                    headers={'content-type': 'application/x-www-form-urlencoded'}
                )
            except Exception as e:
                logger.warning(f"Failed to revoke Google token: {str(e)}")
    
    def check_availability(self, calendar_id: str, start_time, end_time) -> List[Dict]:
        """Check calendar availability"""
        try:
            service = self.get_service()
            
            # Convert times to RFC3339 format; ensure timezone-aware, default UTC
            from datetime import timezone
            def to_rfc3339(dt):
                try:
                    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
                except Exception:
                    return dt

            time_min = to_rfc3339(start_time)
            time_max = to_rfc3339(end_time)
            
            # Get events in the time range
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Extract busy periods
            busy_periods = []
            for event in events:
                if 'transparency' in event and event['transparency'] == 'transparent':
                    continue  # Skip events marked as free
                    
                start = event.get('start', {})
                end = event.get('end', {})
                
                # Handle all-day events and timed events
                start_time = start.get('dateTime', start.get('date'))
                end_time = end.get('dateTime', end.get('date'))
                
                if start_time and end_time:
                    busy_periods.append({
                        'start': start_time,
                        'end': end_time
                    })
            
            return busy_periods
            
        except Exception as e:
            logger.error(f"Failed to check availability: {str(e)}")
            raise
    
    def create_event(self, calendar_id: str, event_data: Dict) -> Dict:
        """Create a calendar event"""
        try:
            service = self.get_service()
            
            # Create event
            event = service.events().insert(
                calendarId=calendar_id,
                body=event_data,
                sendUpdates='all'  # Send invitations to attendees
            ).execute()
            
            logger.info(f"Created event: {event.get('id')}")
            return event
            
        except Exception as e:
            logger.error(f"Failed to create event: {str(e)}")
            raise


# Legacy compatibility class
class CalendarServiceFactory:
    """Factory for creating calendar services - legacy compatibility"""
    
    @staticmethod
    def get_service(calendar):
        """Get appropriate service for a calendar"""
        if calendar.provider == 'google':
            if hasattr(calendar, 'google_calendar'):
                return GoogleCalendarService(calendar.google_calendar)
        return None