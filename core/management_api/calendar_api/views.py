"""Generic Calendar API views - provider-agnostic CRUD operations"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from django.db import transaction

from core.models import Calendar
from .serializers import CalendarSerializer
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
