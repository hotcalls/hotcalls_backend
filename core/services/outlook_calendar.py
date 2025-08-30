"""
Outlook Calendar service for OAuth and Calendar operations (Microsoft Graph API).
"""
import logging
from datetime import timedelta
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests
from django.db import transaction
from django.db.utils import IntegrityError
from django.conf import settings
from django.utils import timezone
from core.models import OutlookCalendar  # type: ignore

logger = logging.getLogger(__name__)


class OutlookOAuthService:
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
        # Force re-consent so newly added scopes are granted
        params['prompt'] = 'consent'

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
    
    @staticmethod
    def get_user_info(access_token: str) -> Dict:
        """Get user information from Microsoft Graph"""
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        resp = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()


class OutlookCalendarService:
    """Main service class for Outlook Calendar operations - static methods for compatibility"""
    
    @staticmethod
    def build_authorize_url(state: str, code_challenge: str, intent: str = None) -> str:
        """Delegate to OAuth service"""
        return OutlookOAuthService.build_authorize_url(state, code_challenge, intent)
    
    @staticmethod
    def exchange_code_for_tokens(code: str, code_verifier: str) -> Dict:
        """Delegate to OAuth service"""
        return OutlookOAuthService.exchange_code_for_tokens(code, code_verifier)
    
    @staticmethod
    def get_user_info(access_token: str) -> Dict:
        """Delegate to OAuth service"""
        return OutlookOAuthService.get_user_info(access_token)
    
    def __init__(self):
        """Initialize service without specific calendar"""
        pass
    
    def discover_and_update_sub_accounts(self, outlook_calendar: OutlookCalendar) -> List[str]:
        """
        Discover additional sub-accounts (delegated/shared calendars) the user has access to
        and create missing OutlookSubAccount entries.

        Returns list of newly created act_as_upn emails.
        """
        created_upns: List[str] = []
        try:
            headers = {'Authorization': f'Bearer {outlook_calendar.access_token}'}

            discovered_upns = set()

            # 1) Primary list of calendars for the user (self + secondary + shared visible under /me)
            try:
                resp = requests.get(
                    'https://graph.microsoft.com/v1.0/me/calendars?$select=id,name,owner,isDefaultCalendar',
                    headers=headers,
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for cal in data.get('value', []):
                        if cal.get('isDefaultCalendar'):
                            # still record the default calendar for self
                            owner_email = (cal.get('owner') or {}).get('address') or outlook_calendar.primary_email
                            discovered_upns.add(owner_email)
                            # upsert self default calendar row
                            self._upsert_sub_account(
                                outlook_calendar,
                                act_as_upn=owner_email,
                                calendar_id=cal.get('id',''),
                                calendar_name=cal.get('name',''),
                                relationship='self',
                                is_default= True
                            )
                            continue
                        owner_email = (cal.get('owner') or {}).get('address') or outlook_calendar.primary_email
                        discovered_upns.add(owner_email)
                        # upsert self secondary or shared (visible under /me)
                        self._upsert_sub_account(
                            outlook_calendar,
                            act_as_upn=owner_email,
                            calendar_id=cal.get('id',''),
                            calendar_name=cal.get('name',''),
                            relationship='self' if owner_email.lower()==(outlook_calendar.primary_email or '').lower() else 'delegate',
                            is_default=False
                        )
            except Exception as e:
                logger.debug(f"Failed to list /me/calendars for discovery: {e}")

            # 2) Also scan calendarGroups to catch calendars not surfaced at top-level
            try:
                resp = requests.get(
                    'https://graph.microsoft.com/v1.0/me/calendarGroups?$expand=calendars($select=id,name,owner,isDefaultCalendar)',
                    headers=headers,
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for grp in data.get('value', []):
                        for cal in (grp.get('calendars') or []):
                            if cal.get('isDefaultCalendar'):
                                owner_email = (cal.get('owner') or {}).get('address') or outlook_calendar.primary_email
                                discovered_upns.add(owner_email)
                                self._upsert_sub_account(
                                    outlook_calendar,
                                    act_as_upn=owner_email,
                                    calendar_id=cal.get('id',''),
                                    calendar_name=cal.get('name',''),
                                    relationship='self' if owner_email.lower()==(outlook_calendar.primary_email or '').lower() else 'delegate',
                                    is_default=True
                                )
                                continue
                            owner_email = (cal.get('owner') or {}).get('address') or outlook_calendar.primary_email
                            discovered_upns.add(owner_email)
                            self._upsert_sub_account(
                                outlook_calendar,
                                act_as_upn=owner_email,
                                calendar_id=cal.get('id',''),
                                calendar_name=cal.get('name',''),
                                relationship='self' if owner_email.lower()==(outlook_calendar.primary_email or '').lower() else 'delegate',
                                is_default=False
                            )
            except Exception as e:
                logger.debug(f"Failed to list /me/calendarGroups for discovery: {e}")

            # Return created UPNs for logging
            created_upns = list(discovered_upns)

        except Exception as e:
            logger.warning(f"Sub-account discovery failed: {e}")

        return created_upns

    def _upsert_sub_account(
        self,
        outlook_calendar: OutlookCalendar,
        act_as_upn: str,
        calendar_id: str,
        calendar_name: str,
        relationship: str,
        is_default: bool,
    ) -> None:
        from core.models import OutlookSubAccount
        if not calendar_id:
            return
        try:
            # First, merge any legacy placeholder row that was created without calendar_id
            with transaction.atomic():
                placeholder = (
                    OutlookSubAccount.objects.select_for_update()
                    .filter(
                        outlook_calendar=outlook_calendar,
                        act_as_upn=act_as_upn.lower(),
                        calendar_id='',
                    )
                    .first()
                )
                if placeholder:
                    placeholder.calendar_id = calendar_id
                    placeholder.calendar_name = calendar_name or ''
                    placeholder.relationship = relationship
                    placeholder.is_default_calendar = is_default
                    placeholder.active = True
                    try:
                        placeholder.save(update_fields=[
                            'calendar_id',
                            'calendar_name',
                            'relationship',
                            'is_default_calendar',
                            'active',
                            'updated_at',
                        ])
                        return
                    except IntegrityError:
                        # If another row with this calendar_id was created concurrently,
                        # drop the placeholder and fall through to update_or_create below
                        try:
                            placeholder.delete()
                        except Exception:
                            pass

            # Normal idempotent upsert keyed by the unique triplet
            OutlookSubAccount.objects.update_or_create(
                outlook_calendar=outlook_calendar,
                act_as_upn=act_as_upn.lower(),
                calendar_id=calendar_id,
                defaults={
                    'calendar_name': calendar_name or '',
                    'relationship': relationship,
                    'is_default_calendar': is_default,
                    'active': True,
                }
            )
        except Exception as e:
            logger.debug(f"Upsert sub-account failed for {act_as_upn}/{calendar_id}: {e}")

    def sync_calendars(self, outlook_calendar: OutlookCalendar) -> List[Dict]:
        """
        Discover sub-accounts and sync calendars from Microsoft Graph.
        Returns list of synced calendar data for each active sub-account.
        """
        synced_calendars = []
        errors = {}
        
        try:
            headers = {'Authorization': f'Bearer {outlook_calendar.access_token}'}
            # Ensure we have up-to-date sub-accounts before syncing
            try:
                self.discover_and_update_sub_accounts(outlook_calendar)
            except Exception as e:
                logger.debug(f"Sub-account discovery during sync failed: {e}")
            
            # Iterate through active sub-accounts
            for sub_account in outlook_calendar.sub_accounts.filter(active=True):
                try:
                    # Determine the API endpoint based on relationship
                    if sub_account.relationship == 'self':
                        # Use 'me' endpoint for self
                        calendar_endpoint = 'https://graph.microsoft.com/v1.0/me/calendar'
                    else:
                        # Use users/{upn} endpoint for delegated/shared
                        upn = sub_account.act_as_upn
                        calendar_endpoint = f'https://graph.microsoft.com/v1.0/users/{upn}/calendar'
                    
                    # Get primary calendar for this sub-account
                    resp = requests.get(calendar_endpoint, headers=headers, timeout=30)
                    
                    if resp.ok:
                        calendar_data = resp.json()
                        
                        synced_data = {
                            'sub_account_id': str(sub_account.id),
                            'calendar_id': calendar_data.get('id'),
                            'act_as_upn': sub_account.act_as_upn,
                            'relationship': sub_account.relationship,
                            'name': calendar_data.get('name', ''),
                            'color': calendar_data.get('color', ''),
                            'can_edit': calendar_data.get('canEdit', False),
                            'can_share': calendar_data.get('canShare', False),
                            'can_view_private_items': calendar_data.get('canViewPrivateItems', False),
                            'owner': calendar_data.get('owner', {}).get('address', ''),
                            'is_default_calendar': calendar_data.get('isDefaultCalendar', False),
                        }
                        
                        # Update external_id for self calendar
                        if sub_account.relationship == 'self' and calendar_data.get('id'):
                            outlook_calendar.external_id = calendar_data.get('id')
                        
                        synced_calendars.append(synced_data)
                        logger.info(f"Synced calendar for sub-account: {sub_account.act_as_upn}")
                        
                    else:
                        error_msg = f"Failed to get calendar for {sub_account.act_as_upn}: {resp.status_code}"
                        errors[sub_account.act_as_upn] = error_msg
                        logger.error(error_msg)
                        
                except Exception as e:
                    error_msg = f"Failed to sync {sub_account.act_as_upn}: {str(e)}"
                    errors[sub_account.act_as_upn] = error_msg
                    logger.error(error_msg)
            
            # Update sync status
            outlook_calendar.last_sync = timezone.now()
            outlook_calendar.sync_errors = errors if errors else {}
            outlook_calendar.save()
            
        except Exception as e:
            logger.error(f"Failed to sync Outlook calendars: {str(e)}")
            outlook_calendar.sync_errors = {'error': str(e), 'timestamp': timezone.now().isoformat()}
            outlook_calendar.save()
            
        return synced_calendars
    
    def revoke_tokens(self, outlook_calendar: OutlookCalendar):
        """Revoke tokens with Microsoft (best effort)"""
        # Microsoft doesn't have a revoke endpoint, just log it
        logger.info(f"Tokens marked for revocation for {outlook_calendar.primary_email}")


class MicrosoftGraphService:
    """Service for Microsoft Graph calendar operations"""

    def __init__(self, outlook_calendar: OutlookCalendar):
        """Initialize with OutlookCalendar model"""
        self.outlook_calendar = outlook_calendar

    def _auth_headers(self) -> Dict[str, str]:
        headers = {
            'Authorization': f'Bearer {self.outlook_calendar.access_token}',
            'Content-Type': 'application/json',
        }
        if self.outlook_calendar.timezone_windows:
            headers['Prefer'] = f'outlook.timezone="{self.outlook_calendar.timezone_windows}"'
        return headers

    def _request(self, method: str, url: str, retry_on_401: bool = True, **kwargs):
        """Do a Graph request with simple 401 refresh and 429 Retry-After handling"""
        resp = requests.request(method, url, headers=self._auth_headers(), timeout=30, **kwargs)
        if resp.status_code == 401 and retry_on_401 and self.outlook_calendar.refresh_token:
            try:
                token = OutlookOAuthService.refresh_tokens(self.outlook_calendar.refresh_token)
                self.outlook_calendar.access_token = token.get('access_token', self.outlook_calendar.access_token)
                self.outlook_calendar.refresh_token = token.get('refresh_token') or self.outlook_calendar.refresh_token
                self.outlook_calendar.token_expires_at = timezone.now() + timedelta(seconds=int(token.get('expires_in', 3600)))
                self.outlook_calendar.save(update_fields=['access_token', 'refresh_token', 'token_expires_at', 'updated_at'])
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
            tz = self.outlook_calendar.timezone_windows or 'UTC'
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
            # mark teams_added when we attempted teams
            if payload.get('teams'):
                data['teams_added'] = True

            # Best-effort: fetch onlineMeeting.joinUrl after creation
            try:
                if payload.get('teams') and isinstance(data, dict) and data.get('id'):
                    event_id = data.get('id')
                    read_url = f'https://graph.microsoft.com/v1.0/me/events/{event_id}'

                    def try_read_join_url_once() -> Optional[str]:
                        try:
                            read_resp = self._request('GET', read_url, retry_on_401=False)
                            if read_resp.ok:
                                read_data = read_resp.json()
                                online_meeting = read_data.get('onlineMeeting')
                                if online_meeting and isinstance(online_meeting, dict):
                                    return online_meeting.get('joinUrl')
                        except Exception:
                            pass
                        return None

                    join_url = try_read_join_url_once()
                    if join_url:
                        data['onlineMeeting'] = {'joinUrl': join_url}
                    else:
                        # Retry once after a short delay
                        import time
                        time.sleep(1)
                        join_url = try_read_join_url_once()
                        if join_url:
                            data['onlineMeeting'] = {'joinUrl': join_url}
            except Exception:
                pass

            return data
        except Exception as e:
            logger.error(f"Microsoft event creation error: {str(e)}")
            raise

    # Subscription methods removed - OAuth only, no webhooks needed