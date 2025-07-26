from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample
from datetime import datetime, timedelta

from core.models import Calendar, CalendarConfiguration
from .serializers import (
    CalendarSerializer, CalendarCreateSerializer,
    CalendarConfigurationSerializer, CalendarConfigurationCreateSerializer,
    CalendarAvailabilityRequestSerializer, CalendarAvailabilityResponseSerializer
)
from .filters import CalendarFilter, CalendarConfigurationFilter
from .permissions import CalendarPermission, CalendarConfigurationPermission


@extend_schema_view(
    list=extend_schema(
        summary="📅 List calendars",
        description="""
        Retrieve calendars based on your workspace access and role.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see calendars in their workspaces (filtered)
        - **Staff Members**: Can view all calendars in the system
        - **Superusers**: Full access to all calendar data
        
        **📊 Response Filtering**:
        - Regular users see only workspace-scoped calendars
        - Staff/Superusers see all calendars with full configuration
        
        **🎯 Use Cases**:
        - Calendar integration overview
        - Scheduling resource management
        - Workspace calendar inventory
        """,
        responses={
            200: OpenApiResponse(
                response=CalendarSerializer(many=True),
                description="✅ Successfully retrieved calendars based on access level"
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access calendars")
        },
        tags=["Calendar Management"]
    ),
    create=extend_schema(
        summary="➕ Create calendar integration",
        description="""
        Create a new calendar integration for a workspace (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot create calendar integrations
        - **✅ Staff Members**: Can create calendar integrations
        - **✅ Superusers**: Can create calendar integrations
        
        **📅 Integration Setup**:
        - Connects external calendar services (Google, Outlook)
        - Establishes authentication with calendar providers
        - Enables scheduling and availability checking
        """,
        request=CalendarCreateSerializer,
        responses={
            201: OpenApiResponse(response=CalendarSerializer, description="✅ Calendar integration created successfully"),
            400: OpenApiResponse(description="❌ Validation error - Check integration settings"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required")
        },
        tags=["Calendar Management"]
    ),
    retrieve=extend_schema(
        summary="Get calendar details",
        description="Retrieve detailed information about a specific calendar",
        tags=["Calendar Management"]
    ),
    update=extend_schema(
        summary="Update calendar",
        description="Update all fields of a calendar (staff only)",
        tags=["Calendar Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update calendar",
        description="Update specific fields of a calendar (staff only)",
        tags=["Calendar Management"]
    ),
    destroy=extend_schema(
        summary="Delete calendar",
        description="Delete a calendar (superuser only)",
        tags=["Calendar Management"]
    ),
)
class CalendarViewSet(viewsets.ModelViewSet):
    """
    📅 **Calendar Integration Management with Workspace-Based Access**
    
    Manages calendar integrations with workspace-filtered access:
    - **👤 Regular Users**: Access only calendars in their workspaces
    - **👔 Staff**: Full calendar administration across all workspaces
    - **🔧 Superusers**: Complete calendar control including deletion
    """
    queryset = Calendar.objects.all()
    permission_classes = [CalendarPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CalendarFilter
    search_fields = ['account_id', 'workspace__workspace_name']
    ordering_fields = ['calendar_type', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CalendarCreateSerializer
        return CalendarSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return Calendar.objects.all()
        else:
            # Regular users can only see calendars in their workspaces
            return Calendar.objects.filter(workspace__users=user)
    
    @extend_schema(
        summary="Get calendar configurations",
        description="Get all configurations for a specific calendar",
        tags=["Calendar Management"]
    )
    @action(detail=True, methods=['get'])
    def configurations(self, request, pk=None):
        """Get all configurations for a specific calendar"""
        calendar = self.get_object()
        configurations = calendar.mapping_calendar_configurations.all()
        serializer = CalendarConfigurationSerializer(configurations, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Test calendar connection",
        description="Test the connection to the calendar service",
        tags=["Calendar Management"]
    )
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test calendar connection"""
        calendar = self.get_object()
        
        # This would contain actual calendar API integration logic
        # For now, return a mock response
        return Response({
            'calendar_id': calendar.id,
            'calendar_type': calendar.calendar_type,
            'account_id': calendar.account_id,
            'connection_status': 'success',
            'message': 'Calendar connection test successful',
            'last_tested': datetime.now().isoformat()
        })


@extend_schema_view(
    list=extend_schema(
        summary="List calendar configurations",
        description="Retrieve a list of all calendar configurations with filtering capabilities",
        tags=["Calendar Management"]
    ),
    create=extend_schema(
        summary="Create a new calendar configuration",
        description="Create a new calendar configuration (staff only)",
        tags=["Calendar Management"]
    ),
    retrieve=extend_schema(
        summary="Get configuration details",
        description="Retrieve detailed information about a specific calendar configuration",
        tags=["Calendar Management"]
    ),
    update=extend_schema(
        summary="Update configuration",
        description="Update all fields of a calendar configuration (staff only)",
        tags=["Calendar Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update configuration",
        description="Update specific fields of a calendar configuration (staff only)",
        tags=["Calendar Management"]
    ),
    destroy=extend_schema(
        summary="Delete configuration",
        description="Delete a calendar configuration (staff only)",
        tags=["Calendar Management"]
    ),
)
class CalendarConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CalendarConfiguration model operations
    
    Provides CRUD operations for calendar configurations:
    - Users can view configurations for calendars in their workspaces
    - Staff can create/modify/delete configurations
    """
    queryset = CalendarConfiguration.objects.all()
    permission_classes = [CalendarConfigurationPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CalendarConfigurationFilter
    search_fields = ['sub_calendar_id', 'calendar__account_id', 'calendar__workspace__workspace_name']
    ordering_fields = ['duration', 'prep_time', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CalendarConfigurationCreateSerializer
        return CalendarConfigurationSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return CalendarConfiguration.objects.all()
        else:
            # Regular users can only see configurations for calendars in their workspaces
            return CalendarConfiguration.objects.filter(
                calendar__workspace__users=user
            )
    
    @extend_schema(
        summary="Check availability",
        description="Check available time slots for a specific date",
        tags=["Calendar Management"]
    )
    @action(detail=True, methods=['post'])
    def check_availability(self, request, pk=None):
        """Check availability for a specific configuration and date"""
        configuration = self.get_object()
        serializer = CalendarAvailabilityRequestSerializer(data=request.data)
        
        if serializer.is_valid():
            date = serializer.validated_data['date']
            duration_minutes = serializer.validated_data['duration_minutes']
            
            # Mock availability logic - replace with actual calendar API integration
            available_slots = []
            current_time = datetime.combine(date, configuration.from_time)
            end_time = datetime.combine(date, configuration.to_time)
            
            while current_time + timedelta(minutes=duration_minutes) <= end_time:
                slot = {
                    'start_time': current_time.time().isoformat(),
                    'end_time': (current_time + timedelta(minutes=duration_minutes)).time().isoformat(),
                    'available': True  # In real implementation, check against calendar API
                }
                available_slots.append(slot)
                current_time += timedelta(minutes=30)  # 30-minute intervals
            
            response_data = {
                'date': date,
                'available_slots': available_slots,
                'calendar_config_id': configuration.id
            }
            
            response_serializer = CalendarAvailabilityResponseSerializer(response_data)
            return Response(response_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 