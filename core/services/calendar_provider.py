"""
Unified calendar provider facade for Google and Outlook providers.

This module exposes provider-agnostic helpers to:
- fetch free/busy intervals for a provider sub-account
- check if a range is busy
- create events on the target calendar
- delete events by id (best-effort, for rollback)

All datetime inputs MUST be timezone-aware and should use the EventType.timezone.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Dict, Optional

from zoneinfo import ZoneInfo

from django.utils import timezone as dj_timezone

from core.models import SubAccount

logger = logging.getLogger(__name__)


@dataclass
class BusyInterval:
    start: datetime
    end: datetime


def _parse_iso_datetime(value: str, tz: ZoneInfo) -> datetime:
    """Parse various ISO8601 strings returned by providers into aware datetimes in tz.
    Handles trailing 'Z' and naive strings by assuming tz.
    """
    if not value:
        raise ValueError("Empty datetime string")
    try:
        # Date-only like 'YYYY-MM-DD' (e.g., all-day events)
        if len(value) == 10 and value[4] == '-' and value[7] == '-':
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=tz)
        # Normalize Zulu suffix to +00:00 for fromisoformat
        if value.endswith('Z'):
            value = value[:-1] + '+00:00'
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # Treat naive as local time in tz
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    except Exception as exc:
        logger.debug(f"Failed to parse ISO datetime '{value}': {exc}")
        # Fallback: treat as naive local time in tz
        try:
            return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz)
        except Exception:
            raise


class CalendarProviderFacade:
    """Facade that routes operations based on SubAccount.provider."""

    @staticmethod
    def free_busy(
        sub_account: SubAccount,
        start: datetime,
        end: datetime,
        timezone_name: str,
    ) -> List[BusyInterval]:
        tz = ZoneInfo(timezone_name)
        provider = (sub_account.provider or '').lower()
        if provider == 'google':
            from core.models import GoogleSubAccount
            from core.services.google_calendar import GoogleCalendarService

            gsub = GoogleSubAccount.objects.select_related('google_calendar').get(id=sub_account.sub_account_id)
            gcal_service = GoogleCalendarService(gsub.google_calendar)
            calendar_id = 'primary' if getattr(gsub, 'relationship', 'self') == 'self' else gsub.act_as_email
            items = gcal_service.check_availability(calendar_id, start, end)
            intervals: List[BusyInterval] = []
            for it in items:
                s = _parse_iso_datetime(it.get('start'), tz)
                e = _parse_iso_datetime(it.get('end'), tz)
                if s < e:
                    intervals.append(BusyInterval(s, e))
            return intervals

        if provider == 'outlook':
            from core.models import OutlookSubAccount
            from core.services.outlook_calendar import MicrosoftGraphService

            osub = OutlookSubAccount.objects.select_related('outlook_calendar').get(id=sub_account.sub_account_id)
            ms = MicrosoftGraphService(osub.outlook_calendar)
            calendar_id = osub.calendar_id
            items = ms.check_availability(calendar_id, start, end)
            intervals = []
            for it in items:
                s = _parse_iso_datetime(it.get('start'), tz)
                e = _parse_iso_datetime(it.get('end'), tz)
                if s < e:
                    intervals.append(BusyInterval(s, e))
            return intervals

        return []

    @staticmethod
    def is_busy(
        sub_account: SubAccount,
        check_start: datetime,
        check_end: datetime,
        timezone_name: str,
    ) -> bool:
        intervals = CalendarProviderFacade.free_busy(sub_account, check_start, check_end, timezone_name)
        for it in intervals:
            if it.start < check_end and it.end > check_start:
                return True
        return False

    @staticmethod
    def create_event(
        sub_account: SubAccount,
        start: datetime,
        end: datetime,
        title: str,
        description: str,
        attendees: Optional[List[Dict]] = None,
        location: str = '',
    ) -> Dict:
        tz = start.tzinfo or ZoneInfo('UTC')
        tz_name = getattr(tz, 'key', 'UTC')
        provider = (sub_account.provider or '').lower()

        if provider == 'google':
            from core.models import GoogleSubAccount
            from core.services.google_calendar import GoogleCalendarService
            gsub = GoogleSubAccount.objects.select_related('google_calendar').get(id=sub_account.sub_account_id)
            gcal_service = GoogleCalendarService(gsub.google_calendar)
            calendar_id = 'primary' if getattr(gsub, 'relationship', 'self') == 'self' else gsub.act_as_email
            body = {
                'summary': title,
                'description': description,
                'start': {'dateTime': start.isoformat(), 'timeZone': tz_name},
                'end': {'dateTime': end.isoformat(), 'timeZone': tz_name},
            }
            if attendees:
                body['attendees'] = [{'email': a.get('email'), 'displayName': a.get('name') or a.get('email')} for a in attendees if a.get('email')]
            if location:
                body['location'] = {'displayName': location}
            return gcal_service.create_event(calendar_id, body)

        if provider == 'outlook':
            from core.models import OutlookSubAccount
            from core.services.outlook_calendar import MicrosoftGraphService
            osub = OutlookSubAccount.objects.select_related('outlook_calendar').get(id=sub_account.sub_account_id)
            ms = MicrosoftGraphService(osub.outlook_calendar)
            payload = {
                'subject': title,
                'body': description,
                'start': start.isoformat(),
                'end': end.isoformat(),
                'attendees': attendees or [],
                'location': location,
                # 'teams': True  # enable if/when Teams is desired via settings
            }
            return ms.create_event(osub.calendar_id, payload, send_invitations=True)

        raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def delete_event(sub_account: SubAccount, event_id: str) -> None:
        provider = (sub_account.provider or '').lower()
        if not event_id:
            return
        try:
            if provider == 'google':
                from core.models import GoogleSubAccount
                from core.services.google_calendar import GoogleCalendarService
                gsub = GoogleSubAccount.objects.select_related('google_calendar').get(id=sub_account.sub_account_id)
                svc = GoogleCalendarService(gsub.google_calendar)
                calendar_id = 'primary' if getattr(gsub, 'relationship', 'self') == 'self' else gsub.act_as_email
                client = svc.get_service()
                client.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates='all').execute()
                return

            if provider == 'outlook':
                from core.models import OutlookSubAccount
                from core.services.outlook_calendar import MicrosoftGraphService
                osub = OutlookSubAccount.objects.select_related('outlook_calendar').get(id=sub_account.sub_account_id)
                ms = MicrosoftGraphService(osub.outlook_calendar)
                # Delete by event id using /me/events/{id}
                url = f'https://graph.microsoft.com/v1.0/me/events/{event_id}'
                resp = ms._request('DELETE', url)
                if resp.status_code not in (200, 202, 204):
                    logger.debug(f"Outlook delete_event non-2xx for {event_id}: {resp.status_code}")
                return
        except Exception as exc:
            logger.warning(f"Failed to delete event {event_id} for provider {provider}: {exc}")
            return


