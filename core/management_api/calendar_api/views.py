"""Generic Calendar API views - provider-agnostic CRUD operations"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from django.db import transaction

from core.models import Calendar
from core.services.google_calendar import GoogleCalendarService
from core.services.outlook_calendar import OutlookCalendarService
from .serializers import CalendarSerializer, CalendarSubAccountSerializer
from .filters import CalendarFilter
from .permissions import CalendarPermission

logger = logging.getLogger(__name__)


@extend_schema_view(
    create=extend_schema(
        summary="➕ Create calendar",
        description="""
        Create a new calendar entry for a workspace.
        
        **Note**: This endpoint creates the generic calendar record only.
        To connect to Google or Outlook, use the provider-specific OAuth endpoints:
        - Google: `/api/google-calendar/auth/authorize`
        - Outlook: `/api/outlook-calendar/auth/authorize`
        """,
        request=CalendarSerializer,
        responses={
            201: OpenApiResponse(
                response=CalendarSerializer,
                description="✅ Calendar created successfully"
            ),
            400: OpenApiResponse(description="❌ Invalid data provided")
        },
        tags=["Calendar Management"]
    ),
    list=extend_schema(
        summary="📅 List calendars",
        description="""
        Retrieve all calendars across providers in your workspaces.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see calendars in their workspaces
        - **Superusers**: Can view all calendars in the system
        
        **📊 Providers Supported**:
        - Google Calendar
        - Outlook Calendar
        
        **🎯 Use Cases**:
        - Calendar overview across all providers
        - Workspace calendar inventory
        - Integration status monitoring
        """,
        responses={
            200: OpenApiResponse(
                response=CalendarSerializer(many=True),
                description="✅ Successfully retrieved calendars"
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Calendar Management"]
    ),
    retrieve=extend_schema(
        summary="📄 Get calendar details",
        description="Retrieve detailed information about a specific calendar",
        responses={
            200: OpenApiResponse(
                response=CalendarSerializer,
                description="✅ Calendar details retrieved"
            ),
            404: OpenApiResponse(description="❌ Calendar not found")
        },
        tags=["Calendar Management"]
    ),
    update=extend_schema(
        summary="✏️ Update calendar",
        description="Update calendar information (name, active status)",
        request=CalendarSerializer,
        responses={
            200: OpenApiResponse(
                response=CalendarSerializer,
                description="✅ Calendar updated successfully"
            ),
            404: OpenApiResponse(description="❌ Calendar not found")
        },
        tags=["Calendar Management"]
    ),
    partial_update=extend_schema(
        summary="📝 Partially update calendar",
        description="Update specific fields of a calendar",
        request=CalendarSerializer,
        responses={
            200: OpenApiResponse(
                response=CalendarSerializer,
                description="✅ Calendar updated successfully"
            ),
            404: OpenApiResponse(description="❌ Calendar not found")
        },
        tags=["Calendar Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete calendar",
        description="""
        Delete a calendar and its provider-specific data.
        
        **⚠️ Warning**: This will also delete:
        - Google Calendar connection (if Google)
        - Outlook Calendar connection (if Outlook)
        - Any associated data
        """,
        responses={
            204: OpenApiResponse(description="✅ Calendar deleted successfully"),
            404: OpenApiResponse(description="❌ Calendar not found")
        },
        tags=["Calendar Management"]
    ),
)
class CalendarViewSet(viewsets.ModelViewSet):
    """
    📅 **Generic Calendar Management**
    
    Provider-agnostic calendar CRUD operations:
    - List all calendars across providers
    - View calendar details
    - Update calendar properties (name, active status)
    - Delete calendars
    
    **Note**: For provider-specific operations (OAuth, sync), use:
    - `/api/google-calendar/` for Google Calendar
    - `/api/outlook-calendar/` for Outlook Calendar
    """
    queryset = Calendar.objects.all()
    serializer_class = CalendarSerializer
    permission_classes = [CalendarPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CalendarFilter
    search_fields = ['name', 'workspace__workspace_name']
    ordering_fields = ['name', 'provider', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        
        # Superusers can see all calendars
        if user.is_superuser:
            return Calendar.objects.filter(active=True).select_related(
                'workspace'
            ).prefetch_related('google_calendar', 'outlook_calendar')

        # Regular users: only calendars in their workspaces
        return Calendar.objects.filter(
            workspace__users=user,
            active=True
        ).select_related(
            'workspace'
        ).prefetch_related('google_calendar', 'outlook_calendar')
    
    def destroy(self, request, *args, **kwargs):
        """
        Delete a calendar and cascade to provider-specific data.
        The CASCADE on the OneToOne relationship will handle cleanup.
        """
        calendar = self.get_object()
        calendar_id = calendar.id
        provider = calendar.provider
        
        try:
            with transaction.atomic():
                # The CASCADE will delete GoogleCalendar or OutlookCalendar
                response = super().destroy(request, *args, **kwargs)

                logger.info(f"Deleted {provider} calendar {calendar_id} for user {request.user.email}")
                return response
            
        except Exception as e:
            logger.error(f"Failed to delete calendar {calendar_id}: {e}")
            return Response(
                {'error': 'Failed to delete calendar', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        summary="📒 List sub-accounts for a calendar",
        description="Return provider-specific sub-accounts (Google/Outlook) for a given calendar in a unified shape.",
        responses={200: OpenApiResponse(response=CalendarSubAccountSerializer(many=True), description="Sub-accounts")},
        tags=["Calendar Management"],
    )
    @action(detail=True, methods=['get'], url_path='sub-accounts')
    def sub_accounts(self, request, pk=None):
        """List sub-accounts for this calendar in a provider-agnostic format."""
        calendar = self.get_object()
        items = []
        try:
            if calendar.provider == 'google' and hasattr(calendar, 'google_calendar'):
                gc = calendar.google_calendar
                for s in gc.sub_accounts.all():
                    items.append({
                        'id': s.id,
                        'provider': 'google',
                        'address': s.act_as_email,
                        'calendar_name': getattr(s, 'calendar_name', ''),
                        'relationship': s.relationship,
                        'is_default': getattr(s, 'active', False) and (getattr(s, 'relationship', '') == 'self' or getattr(s, 'primary', False)),
                    })
            elif calendar.provider == 'outlook' and hasattr(calendar, 'outlook_calendar'):
                oc = calendar.outlook_calendar
                for s in oc.sub_accounts.all():
                    items.append({
                        'id': s.id,
                        'provider': 'outlook',
                        'address': s.act_as_upn,
                        'calendar_name': getattr(s, 'calendar_name', ''),
                        'relationship': s.relationship,
                        'is_default': bool(getattr(s, 'is_default_calendar', False)),
                    })
        except Exception as e:
            logger.error(f"Failed to list sub-accounts for calendar {calendar.id}: {e}")
            items = []

        serializer = CalendarSubAccountSerializer(items, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="🔄 Sync a calendar",
        description="Run a provider-specific sync for this calendar to refresh metadata and clear previous sync errors.",
        request=None,
        responses={200: OpenApiResponse(response=CalendarSerializer, description="Calendar after sync")},
        tags=["Calendar Management"],
    )
    @action(detail=True, methods=['post'], url_path='sync')
    def sync(self, request, pk=None):
        calendar = self.get_object()
        try:
            if calendar.provider == 'google' and hasattr(calendar, 'google_calendar'):
                service = GoogleCalendarService()
                service.sync_calendars(calendar.google_calendar)
            elif calendar.provider == 'outlook' and hasattr(calendar, 'outlook_calendar'):
                service = OutlookCalendarService()
                service.sync_calendars(calendar.outlook_calendar)
            else:
                return Response({'error': 'No provider connection attached to this calendar'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Failed to sync calendar {calendar.id}: {e}")
            # Provider services already record sync_errors; continue to return current state
        # Refresh instance
        calendar.refresh_from_db()
        return Response(CalendarSerializer(calendar).data)
