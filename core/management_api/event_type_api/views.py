from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta, time
from typing import List, Tuple
from zoneinfo import ZoneInfo
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from core.models import EventType, Workspace, SubAccount
from core.management_api.payment_api.permissions import IsWorkspaceMember
from core.services.calendar_provider import CalendarProviderFacade
import base64
from .serializers import (
    EventTypeSerializer,
    EventTypeCreateUpdateSerializer,
    SubAccountListItemSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List event types", tags=["Event Types"]),
    retrieve=extend_schema(summary="Get event type", tags=["Event Types"]),
    create=extend_schema(summary="Create event type", tags=["Event Types"]),
    partial_update=extend_schema(summary="Update event type", tags=["Event Types"]),
    destroy=extend_schema(summary="Delete event type", tags=["Event Types"]),
)
class EventTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    lookup_field = 'pk'

    def get_permissions(self):
        # Public access for availability lookup and booking (no authentication)
        if getattr(self, 'action', None) in ['availability', 'book']:
            return [AllowAny()]
        return [perm() for perm in self.permission_classes]

    def get_workspace(self) -> Workspace:
        workspace_id = self.kwargs.get('workspace_id') or self.request.query_params.get('workspace_id')
        return get_object_or_404(Workspace, id=workspace_id)

    def get_queryset(self):
        workspace = self.get_workspace()
        return EventType.objects.filter(workspace=workspace).order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EventTypeCreateUpdateSerializer
        return EventTypeSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['workspace'] = self.get_workspace()
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event_type = serializer.save()
        return Response(EventTypeSerializer(event_type).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        event_type = serializer.save()
        return Response(EventTypeSerializer(event_type).data)

    @extend_schema(
        summary="List workspace sub-accounts",
        responses={200: SubAccountListItemSerializer(many=True)},
        tags=["Event Types"]
    )
    def list_subaccounts(self, request, *args, **kwargs):
        """
        Return workspace sub-accounts directly from provider models.

        Optional query param: ?provider=google|outlook to filter.
        """
        workspace = self.get_workspace()
        provider_filter = (request.query_params.get('provider') or '').lower().strip()

        items = []

        # GOOGLE
        if provider_filter in ('', 'google'):
            try:
                from core.models import GoogleSubAccount, SubAccount
                gsubs = (
                    GoogleSubAccount.objects
                    .filter(google_calendar__calendar__workspace=workspace, active=True)
                    .select_related('google_calendar', 'google_calendar__calendar')
                    .order_by('calendar_name', 'act_as_email')
                )
                for g in gsubs:
                    # Ensure router SubAccount exists for this user and provider-specific id
                    sub, _ = SubAccount.objects.get_or_create(
                        owner=request.user,
                        provider='google',
                        sub_account_id=str(g.id),
                    )
                    items.append({
                        'id': sub.id,
                        'provider': 'google',
                        'label': (g.calendar_name or g.act_as_email),
                    })
            except Exception:
                pass

        # OUTLOOK
        if provider_filter in ('', 'outlook'):
            try:
                from core.models import OutlookSubAccount, SubAccount
                osubs = (
                    OutlookSubAccount.objects
                    .filter(outlook_calendar__calendar__workspace=workspace, active=True)
                    .select_related('outlook_calendar', 'outlook_calendar__calendar')
                    .order_by('calendar_name', 'act_as_upn')
                )
                for o in osubs:
                    sub, _ = SubAccount.objects.get_or_create(
                        owner=request.user,
                        provider='outlook',
                        sub_account_id=str(o.id),
                    )
                    items.append({
                        'id': sub.id,
                        'provider': 'outlook',
                        'label': (o.calendar_name or o.act_as_upn),
                    })
            except Exception:
                pass

        # If router table SubAccount has entries, include those too (legacy compatibility)
        try:
            member_ids = workspace.users.values_list('id', flat=True)
            subs = SubAccount.objects.filter(owner_id__in=member_ids).order_by('provider', 'id')
            for s in subs:
                # Avoid duplicates if provider-specific IDs already present
                if any(str(it['id']) == str(s.id) for it in items if it['provider'] == s.provider):
                    continue
                label = s.sub_account_id
                try:
                    if s.provider == 'google':
                        from core.models import GoogleSubAccount
                        g = GoogleSubAccount.objects.filter(id=s.sub_account_id).first()
                        if g:
                            label = g.calendar_name or g.act_as_email
                    elif s.provider == 'outlook':
                        from core.models import OutlookSubAccount
                        o = OutlookSubAccount.objects.filter(id=s.sub_account_id).first()
                        if o:
                            label = o.calendar_name or o.act_as_upn
                except Exception:
                    pass
                items.append({
                    'id': s.id,  # return router id
                    'provider': s.provider,
                    'label': label,
                })
        except Exception:
            pass

        return Response(SubAccountListItemSerializer(items, many=True).data)



    @extend_schema(
        summary="Get availability for a date",
        description="Return available start times for the given date in the EventType.timezone.",
        responses={200: OpenApiResponse(description="List of slots in EventType.timezone")},
        tags=["Event Types"],
    )
    def availability(self, request, *args, **kwargs):
        """
        Two modes supported:
        1) Legacy (frontend): ?date=YYYY-MM-DD
           - Returns envelope with slots as ISO strings (backward compatible)

        2) Agent-friendly: ?from=<ISO8601>&to=<ISO8601>
           - from/to must be within the same calendar day
           - Returns a bare JSON array of slot objects with id/start/end/timezone
        """
        event_type: EventType = self.get_object()
        from_str = (request.query_params.get('from') or '').strip()
        to_str = (request.query_params.get('to') or '').strip()
        date_str = (request.query_params.get('date') or '').strip()

        tz = ZoneInfo(event_type.timezone or 'UTC')

        # Helper: merge intervals
        def merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
            if not intervals:
                return []
            intervals.sort(key=lambda x: x[0])
            merged: List[Tuple[datetime, datetime]] = []
            cur_s, cur_e = intervals[0]
            for s, e in intervals[1:]:
                if s <= cur_e:
                    if e > cur_e:
                        cur_e = e
                else:
                    merged.append((cur_s, cur_e))
                    cur_s, cur_e = s, e
            merged.append((cur_s, cur_e))
            return merged

        def compute_slots_for_window(window_start: datetime, window_end: datetime) -> List[Tuple[datetime, datetime]]:
            # Aggregate busy intervals across mappings
            mappings = list(event_type.calendar_mappings.select_related('sub_account').all())
            busy: List[Tuple[datetime, datetime]] = []
            for m in mappings:
                sub = m.sub_account
                try:
                    items = CalendarProviderFacade.free_busy(sub, window_start, window_end, event_type.timezone)
                    for it in items:
                        busy.append((it.start, it.end))
                except Exception:
                    continue

            # Extend busy intervals by pre-buffers
            before_minutes = (event_type.buffer_time or 0) * 60 + (event_type.prep_time or 0)
            extended_busy: List[Tuple[datetime, datetime]] = []
            if busy:
                for s, e in busy:
                    extended_busy.append((s - timedelta(minutes=before_minutes), e))

            merged_busy_local = merge_intervals(extended_busy)

            # Start from the provided window and subtract busy
            candidates: List[Tuple[datetime, datetime]] = [(window_start, window_end)]
            for bs, be in merged_busy_local:
                new_candidates: List[Tuple[datetime, datetime]] = []
                for cs, ce in candidates:
                    if be <= cs or bs >= ce:
                        new_candidates.append((cs, ce))
                        continue
                    if bs > cs:
                        new_candidates.append((cs, bs))
                    if be < ce:
                        new_candidates.append((be, ce))
                candidates = [(s, e) for (s, e) in new_candidates if e > s]

            # Step through by duration
            duration_minutes = event_type.duration
            step = timedelta(minutes=duration_minutes)
            slot_ranges: List[Tuple[datetime, datetime]] = []
            for s, e in candidates:
                t = s
                while t + step <= e:
                    slot_ranges.append((t, t + step))
                    t = t + step
            return slot_ranges

        # Agent-friendly windowed availability
        if from_str and to_str:
            try:
                def parse_iso(s: str) -> datetime:
                    return datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None
                raw_start = parse_iso(from_str)
                raw_end = parse_iso(to_str)
                if not raw_start or not raw_end:
                    raise ValueError
            except Exception:
                return Response({"error": "invalid from/to format; expected ISO8601"}, status=status.HTTP_400_BAD_REQUEST)

            # Localize to event type timezone
            start_dt = raw_start.astimezone(tz)
            end_dt = raw_end.astimezone(tz)
            if start_dt.date() != end_dt.date():
                return Response({"error": "from/to must be within the same calendar day"}, status=status.HTTP_400_BAD_REQUEST)

            # Respect working hours for that weekday
            weekday = start_dt.weekday()
            working_hour = event_type.working_hours.filter(day_of_week=weekday).first()
            if not working_hour:
                return Response([], status=status.HTTP_200_OK)

            work_start_dt = datetime.combine(start_dt.date(), working_hour.start_time).replace(tzinfo=tz)
            work_end_dt = datetime.combine(start_dt.date(), working_hour.end_time).replace(tzinfo=tz)
            if work_end_dt <= work_start_dt:
                return Response([], status=status.HTTP_200_OK)

            window_start = max(work_start_dt, start_dt)
            window_end = min(work_end_dt, end_dt)
            if window_end <= window_start:
                return Response([], status=status.HTTP_200_OK)

            slot_ranges = compute_slots_for_window(window_start, window_end)

            def encode_slot_id(dt: datetime) -> str:
                iso = dt.isoformat()
                return base64.urlsafe_b64encode(iso.encode()).decode()

            slots_obj = [
                {
                    "id": encode_slot_id(s),
                    "start": s.isoformat(),
                    "end": e.isoformat(),
                    "timezone": event_type.timezone,
                }
                for (s, e) in slot_ranges
            ]
            return Response(slots_obj, status=status.HTTP_200_OK)

        # Legacy per-day availability (date)
        if not date_str:
            return Response({"error": "date is required (YYYY-MM-DD) or pass from/to"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return Response({"error": "invalid date format; expected YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        # Working hours for weekday
        weekday = target_date.weekday()  # 0=Mon
        working_hour = event_type.working_hours.filter(day_of_week=weekday).first()
        if not working_hour:
            return Response({
                "event_type_id": str(event_type.id),
                "date": date_str,
                "timezone": event_type.timezone,
                "slots": [],
            })

        day_start_dt = datetime.combine(target_date, time(0, 0)).replace(tzinfo=tz)
        day_end_dt = day_start_dt + timedelta(days=1)
        work_start_dt = datetime.combine(target_date, working_hour.start_time).replace(tzinfo=tz)
        work_end_dt = datetime.combine(target_date, working_hour.end_time).replace(tzinfo=tz)
        if work_end_dt <= work_start_dt:
            return Response({
                "event_type_id": str(event_type.id),
                "date": date_str,
                "timezone": event_type.timezone,
                "slots": [],
            })

        slot_ranges = compute_slots_for_window(work_start_dt, work_end_dt)
        slot_strs: List[str] = [s.isoformat() for (s, _e) in slot_ranges]
        return Response({
            "event_type_id": str(event_type.id),
            "date": date_str,
            "timezone": event_type.timezone,
            "slots": slot_strs,
        })

    @extend_schema(
        summary="Book a slot",
        description="Create events on all target calendars for this EventType. Body requires only 'start' (ISO) in EventType.timezone.",
        responses={201: OpenApiResponse(description="Booking created and ICS returned.")},
        tags=["Event Types"],
    )
    def book(self, request, *args, **kwargs):
        event_type: EventType = self.get_object()
        tz = ZoneInfo(event_type.timezone or 'UTC')

        data = request.data if isinstance(request.data, dict) else {}
        start_str = (data.get('start') or '').strip()
        slot_id = (data.get('slot_id') or '').strip()

        if not start_str and not slot_id:
            return Response({"error": "start or slot_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not start_str and slot_id:
            try:
                decoded = base64.urlsafe_b64decode(slot_id.encode()).decode()
                start_str = decoded
            except Exception:
                return Response({"error": "invalid slot_id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Parse start in event type timezone if naive
            if start_str.endswith('Z'):
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(tz)
            else:
                parsed = datetime.fromisoformat(start_str)
                start_dt = parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed.astimezone(tz)
        except Exception:
            return Response({"error": "invalid start format; expected ISO8601"}, status=status.HTTP_400_BAD_REQUEST)

        end_dt = start_dt + timedelta(minutes=event_type.duration)

        # Final conflict check across all calendars with pre-buffers
        before_minutes = (event_type.buffer_time or 0) * 60 + (event_type.prep_time or 0)
        check_start = start_dt - timedelta(minutes=before_minutes)
        check_end = end_dt

        mappings = list(event_type.calendar_mappings.select_related('sub_account').all())
        for m in mappings:
            sub = m.sub_account
            try:
                if CalendarProviderFacade.is_busy(sub, check_start, check_end, event_type.timezone):
                    return Response({"error": "slot no longer available"}, status=status.HTTP_409_CONFLICT)
            except Exception:
                # Be conservative on provider errors: treat as conflict
                return Response({"error": "slot check failed"}, status=status.HTTP_409_CONFLICT)

        # Create on all targets
        title = event_type.name
        description = f"Booking for {event_type.name}"
        attendees = []
        created_events: List[Tuple[SubAccount, dict]] = []
        try:
            for m in mappings:
                if m.role != 'target':
                    continue
                sub = m.sub_account
                ev = CalendarProviderFacade.create_event(
                    sub_account=sub,
                    start=start_dt,
                    end=end_dt,
                    title=title,
                    description=description,
                    attendees=attendees,
                )
                created_events.append((sub, ev))
        except Exception as exc:
            # Rollback already created
            for sub, ev in created_events:
                try:
                    CalendarProviderFacade.delete_event(sub, (ev or {}).get('id'))
                except Exception:
                    pass
            return Response({"error": "failed to create events", "details": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        # Generate ICS
        import uuid
        uid = f"{uuid.uuid4()}@hotcalls"
        def to_ics_dt(dt: datetime) -> str:
            # Local time with TZID; format: YYYYMMDDTHHMMSS
            return dt.strftime("%Y%m%dT%H%M%S")

        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//HotCalls//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{to_ics_dt(datetime.now(tz))}",
            f"DTSTART;TZID={event_type.timezone}:{to_ics_dt(start_dt)}",
            f"DTEND;TZID={event_type.timezone}:{to_ics_dt(end_dt)}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        ics_content = "\r\n".join(ics_lines) + "\r\n"

        return Response({
            "status": "success",
            "event_type_id": str(event_type.id),
            "timezone": event_type.timezone,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "created_event_ids": [ (ev or {}).get('id') for (_, ev) in created_events ],
            "ics": ics_content,
        }, status=status.HTTP_201_CREATED)

