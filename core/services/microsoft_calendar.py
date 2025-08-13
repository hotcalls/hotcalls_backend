"""
Microsoft 365 / Exchange Online service for OAuth and Calendar operations (Graph API).
Minimal skeleton to mirror Google integration style.
"""
import logging
from datetime import timedelta, timezone as dt_timezone
from typing import Dict, List
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone
from core.models import Calendar, MicrosoftCalendar, MicrosoftCalendarConnection, MicrosoftSubscription  # type: ignore

logger = logging.getLogger(__name__)


class MicrosoftOAuthService:
    """Service for Microsoft OAuth (Auth Code + PKCE)"""

    @staticmethod
    def build_authorize_url(state: str, code_challenge: str, intent: str = None) -> str:
        tenant = getattr(settings, 'MS_AUTH_TENANT', 'organizations')
        client_id = getattr(settings, 'MS_CLIENT_ID', '')
        redirect_uri = getattr(settings, 'MS_REDIRECT_URI', '')
        scopes = getattr(settings, 'MS_SCOPES', [])

        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'response_mode': 'query',
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        if intent:
            params['prompt'] = 'select_account'

        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}"

    @staticmethod
    def exchange_code_for_tokens(code: str, code_verifier: str) -> Dict:
        tenant = getattr(settings, 'MS_AUTH_TENANT', 'organizations')
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        data = {
            'client_id': getattr(settings, 'MS_CLIENT_ID', ''),
            'client_secret': getattr(settings, 'MS_CLIENT_SECRET', ''),
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': getattr(settings, 'MS_REDIRECT_URI', ''),
            'code_verifier': code_verifier,
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp = requests.post(token_url, data=data, headers=headers, timeout=30)
        resp.raise_for_status()
        token = resp.json()
        return token

    @staticmethod
    def refresh_tokens(refresh_token: str) -> Dict:
        tenant = getattr(settings, 'MS_AUTH_TENANT', 'organizations')
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        data = {
            'client_id': getattr(settings, 'MS_CLIENT_ID', ''),
            'client_secret': getattr(settings, 'MS_CLIENT_SECRET', ''),
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'redirect_uri': getattr(settings, 'MS_REDIRECT_URI', ''),
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp = requests.post(token_url, data=data, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()


class MicrosoftCalendarService:
    """Service for Microsoft Graph calendar operations"""

    def __init__(self, microsoft_calendar_or_connection):
        # Accept either a MicrosoftCalendar model (to be added) or a connection (dict-like for now)
        self.mc = microsoft_calendar_or_connection
        self.connection = getattr(microsoft_calendar_or_connection, 'connection', microsoft_calendar_or_connection)

    def _auth_headers(self) -> Dict[str, str]:
        token = getattr(self.connection, 'access_token', None) or self.connection.get('access_token')
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        tz = getattr(self.connection, 'timezone_windows', None) or self.connection.get('timezone_windows')
        if tz:
            headers['Prefer'] = f'outlook.timezone="{tz}"'
        return headers

    def _request(self, method: str, url: str, retry_on_401: bool = True, **kwargs):
        """Do a Graph request with simple 401 refresh and 429 Retry-After handling"""
        resp = requests.request(method, url, headers=self._auth_headers(), timeout=30, **kwargs)
        if resp.status_code == 401 and retry_on_401 and getattr(self.connection, 'refresh_token', None):
            try:
                token = MicrosoftOAuthService.refresh_tokens(self.connection.refresh_token)
                self.connection.access_token = token.get('access_token', self.connection.access_token)
                self.connection.refresh_token = token.get('refresh_token') or self.connection.refresh_token
                self.connection.token_expires_at = timezone.now() + timedelta(seconds=int(token.get('expires_in', 3600)))
                self.connection.save(update_fields=['access_token', 'refresh_token', 'token_expires_at', 'updated_at'])
            except Exception:
                return resp
            resp = requests.request(method, url, headers=self._auth_headers(), timeout=30, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get('Retry-After', '1'))
            try:
                import time
                time.sleep(min(retry_after, 3))
                resp = requests.request(method, url, headers=self._auth_headers(), timeout=30, **kwargs)
            except Exception:
                pass
        return resp

    def test_connection(self) -> Dict:
        try:
            resp = self._request('GET', 'https://graph.microsoft.com/v1.0/me')
            if resp.status_code == 401:
                return {'success': False, 'error': 'unauthorized'}
            resp.raise_for_status()
            return {'success': True, 'message': 'Connection successful'}
        except Exception as e:
            logger.error(f"Microsoft connection test failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def sync_calendars(self) -> List[dict]:
        calendars: List[dict] = []
        try:
            # Get primary calendar id
            primary_id = None
            try:
                primary_resp = self._request('GET', 'https://graph.microsoft.com/v1.0/me/calendar')
                if primary_resp.ok:
                    primary_id = (primary_resp.json() or {}).get('id')
            except Exception:
                primary_id = None

            resp = self._request('GET', 'https://graph.microsoft.com/v1.0/me/calendars')
            resp.raise_for_status()
            data = resp.json().get('value', [])
            for item in data:
                external_id = item.get('id')
                name = item.get('name')
                # Upsert generic Calendar
                calendar, _ = Calendar.objects.update_or_create(
                    workspace=self.connection.workspace,
                    name=name,
                    provider='outlook',
                    defaults={'active': True}
                )
                # Upsert MicrosoftCalendar
                MicrosoftCalendar.objects.update_or_create(
                    external_id=external_id,
                    defaults={
                        'calendar': calendar,
                        'connection': self.connection,
                        'primary': bool(primary_id and external_id == primary_id),
                        'can_edit': True,
                    }
                )
                calendars.append({'external_id': external_id, 'name': name})
            return calendars
        except Exception as e:
            logger.error(f"Failed to sync Microsoft calendars: {str(e)}")
            raise

    def check_availability(self, calendar_id: str, start_time, end_time) -> List[Dict]:
        """Return busy periods using calendarView between start_time and end_time"""
        try:
            params = {
                'startDateTime': start_time.isoformat(),
                'endDateTime': end_time.isoformat(),
                '$top': 500,
            }
            url = f'https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/calendarView'
            resp = self._request('GET', url, params=params)
            if resp.status_code == 401:
                return []
            resp.raise_for_status()
            items = resp.json().get('value', [])
            busy = []
            for ev in items:
                try:
                    start = ev.get('start', {})
                    end = ev.get('end', {})
                    start_dt = start.get('dateTime')
                    end_dt = end.get('dateTime')
                    if start_dt and end_dt:
                        busy.append({'start': start_dt, 'end': end_dt})
                except Exception:
                    continue
            return busy
        except Exception as e:
            logger.error(f"Microsoft availability error: {str(e)}")
            raise

    def create_event(self, calendar_id: str, payload: Dict, send_invitations: bool = True) -> Dict:
        """Create event in a Microsoft calendar. Payload expects generic fields.
        Expected keys: subject, body, start (iso), end (iso), attendees(list of {email,name,type}), location, teams(bool)
        """
        try:
            tz = getattr(self.connection, 'timezone_windows', None) or 'UTC'
            attendees = []
            for a in payload.get('attendees', []):
                attendees.append({
                    'emailAddress': {'address': a.get('email'), 'name': a.get('name') or a.get('email')},
                    'type': a.get('type', 'required').capitalize()
                })
            body = {
                'subject': payload.get('subject') or payload.get('summary', ''),
                'body': {'contentType': 'HTML', 'content': payload.get('body') or payload.get('description', '')},
                'start': {'dateTime': payload.get('start'), 'timeZone': tz},
                'end': {'dateTime': payload.get('end'), 'timeZone': tz},
                'attendees': attendees,
            }
            if payload.get('location'):
                body['location'] = {'displayName': payload.get('location')}
            if payload.get('teams'):
                body['isOnlineMeeting'] = True
                body['onlineMeetingProvider'] = 'teamsForBusiness'

            params = {'sendInvitations': 'true' if send_invitations else 'false'}
            url = f'https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/events'
            resp = self._request('POST', url, json=body, params=params)
            if resp.status_code == 403 and payload.get('teams'):
                # Fallback: retry without Teams
                body.pop('isOnlineMeeting', None)
                body.pop('onlineMeetingProvider', None)
                resp = self._request('POST', url, json=body, params=params)
                resp.raise_for_status()
                data = resp.json()
                data['teams_added'] = False
                return data
            resp.raise_for_status()
            data = resp.json()

            # Best-effort: fetch onlineMeeting.joinUrl after creation, as Graph may not include it in POST response
            try:
                if payload.get('teams') and isinstance(data, dict) and data.get('id'):
                    event_id = data.get('id')
                    read_url = f'https://graph.microsoft.com/v1.0/me/events/{event_id}'
                    # First try $select=onlineMeeting
                    read = self._request('GET', read_url, params={'$select': 'onlineMeeting'})
                    if read.ok:
                        read_json = read.json() or {}
                        if read_json.get('onlineMeeting'):
                            data['onlineMeeting'] = read_json.get('onlineMeeting')
                        else:
                            # Fallback attempt with $expand
                            read2 = self._request('GET', read_url, params={'$expand': 'onlineMeeting'})
                            if read2.ok:
                                read2_json = read2.json() or {}
                                if read2_json.get('onlineMeeting'):
                                    data['onlineMeeting'] = read2_json.get('onlineMeeting')
            except Exception:
                # Do not fail booking if link cannot be read; the event is created and invitations are sent by provider
                pass

            return data
        except Exception as e:
            logger.error(f"Microsoft create_event failed: {str(e)}")
            raise

    def update_event(self, calendar_id: str, event_id: str, updates: Dict, send_updates: str = 'all') -> Dict:
        try:
            tz = getattr(self.connection, 'timezone_windows', None) or 'UTC'
            body: Dict = {}
            if 'subject' in updates:
                body['subject'] = updates['subject']
            if 'body' in updates:
                body['body'] = {'contentType': 'HTML', 'content': updates['body']}
            if 'start' in updates:
                body['start'] = {'dateTime': updates['start'], 'timeZone': tz}
            if 'end' in updates:
                body['end'] = {'dateTime': updates['end'], 'timeZone': tz}
            if 'attendees' in updates:
                attendees = []
                for a in updates.get('attendees', []):
                    attendees.append({
                        'emailAddress': {'address': a.get('email'), 'name': a.get('name') or a.get('email')},
                        'type': a.get('type', 'required').capitalize()
                    })
                body['attendees'] = attendees
            params = {'sendUpdates': send_updates}
            url = f'https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/events/{event_id}'
            resp = self._request('PATCH', url, json=body, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Microsoft update_event failed: {str(e)}")
            raise

    def delete_event(self, calendar_id: str, event_id: str, send_cancellation: bool = True) -> bool:
        try:
            params = {'sendCancellation': 'true' if send_cancellation else 'false'}
            url = f'https://graph.microsoft.com/v1.0/me/calendars/{calendar_id}/events/{event_id}'
            resp = self._request('DELETE', url, params=params)
            if resp.status_code in (204, 200):
                return True
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Microsoft delete_event failed: {str(e)}")
            raise

    def create_subscription(self, client_state: str, days: int = 2, notification_url: str | None = None) -> Dict:
        """Create a subscription for me/events"""
        try:
            expiration = (timezone.now() + timedelta(days=days)).replace(microsecond=0).isoformat()
            url = 'https://graph.microsoft.com/v1.0/subscriptions'
            body = {
                'changeType': 'created,updated,deleted',
                'notificationUrl': notification_url or f"{getattr(settings, 'SITE_URL', '')}/api/webhooks/microsoft/webhook/",
                'resource': 'me/events',
                'expirationDateTime': expiration,
                'clientState': client_state,
            }
            resp = self._request('POST', url, json=body)
            resp.raise_for_status()
            data = resp.json()
            # Persist
            MicrosoftSubscription.objects.update_or_create(
                subscription_id=data['id'],
                defaults={
                    'connection': self.connection,
                    'resource': data.get('resource', 'me/events'),
                    'client_state': client_state,
                    'expiration_at': timezone.datetime.fromisoformat(data['expirationDateTime'].replace('Z', '+00:00')),
                }
            )
            return data
        except Exception as e:
            logger.error(f"Microsoft create_subscription failed: {str(e)}")
            raise

    def renew_subscription(self, subscription_id: str, days: int = 2) -> Dict:
        try:
            expiration = (timezone.now() + timedelta(days=days)).replace(microsecond=0).isoformat()
            url = f'https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}'
            resp = self._request('PATCH', url, json={'expirationDateTime': expiration})
            resp.raise_for_status()
            data = resp.json()
            # Update record
            try:
                sub = MicrosoftSubscription.objects.get(subscription_id=subscription_id)
                sub.expiration_at = timezone.datetime.fromisoformat(data['expirationDateTime'].replace('Z', '+00:00'))
                sub.save(update_fields=['expiration_at', 'updated_at'])
            except MicrosoftSubscription.DoesNotExist:
                pass
            return data
        except Exception as e:
            logger.error(f"Microsoft renew_subscription failed: {str(e)}")
            raise


