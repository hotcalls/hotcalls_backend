from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from core.models import EventType, Workspace, SubAccount
from core.management_api.payment_api.permissions import IsWorkspaceMember
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


