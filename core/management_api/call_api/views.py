from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample
from django.db import transaction
from django.utils import timezone
import json

from core.models import CallLog, Lead, Agent
from .serializers import (
    CallLogSerializer, CallLogCreateSerializer, CallLogAnalyticsSerializer,
    CallLogStatusAnalyticsSerializer, CallLogAgentPerformanceSerializer,
    CallLogAppointmentStatsSerializer, OutboundCallSerializer
)
from .filters import CallLogFilter
from .permissions import CallLogPermission, CallLogAnalyticsPermission


@extend_schema_view(
    list=extend_schema(
        summary="📱 List call logs",
        description="""
        Retrieve all call logs in the system with filtering and search capabilities.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view all call logs
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **📊 Universal Call Access**:
        - All users can view complete call history
        - Comprehensive call data for analysis
        - Historical call information for all leads
        
        **🎯 Use Cases**:
        - Call history review and analysis
        - Performance monitoring and reporting
        - Lead interaction tracking
        - Agent activity oversight
        
        **🔍 New Filtering Options**:
        - Filter by agent and workspace
        - Filter by call status (terminvereinbart, nicht erreicht, etc.)
        - Filter by appointment dates
        - Search includes agent workspace names
        """,
        responses={
            200: OpenApiResponse(
                response=CallLogSerializer(many=True),
                description="✅ Successfully retrieved all call logs",
                examples=[
                    OpenApiExample(
                        'Call Logs List',
                        summary='Recent call activity with new fields',
                        value={
                            'count': 500,
                            'results': [
                                {
                                    'id': 'call-uuid-1',
                                    'lead_name': 'John Smith',
                                    'agent': 'agent-uuid-1',
                                    'agent_workspace_name': 'Sales Team',
                                    'timestamp': '2024-01-15T09:30:00Z',
                                    'direction': 'outbound',
                                    'duration': 180,
                                    'status': 'terminvereinbart',
                                    'appointment_datetime': '2024-01-20T14:00:00Z',
                                    'from_number': '+1234567890',
                                    'to_number': '+1987654321',
                                    'disconnection_reason': 'completed'
                                }
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access call logs")
        },
        tags=["Call Management"]
    ),
    create=extend_schema(
        summary="➕ Create call log",
        description="""
        Create a new call log entry (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot create call logs
        - **✅ Staff Members**: Can create call log entries
        - **✅ Superusers**: Can create call log entries
        
        **📱 System-Generated Data**:
        - Typically created automatically by call systems
        - Manual entry for data correction or import
        - Integration with telephony systems
        
        **📝 Required Information**:
        - `lead`: Associated lead ID
        - `agent`: Agent who made/received the call
        - `from_number`, `to_number`: Phone numbers involved
        - `duration`: Call duration in seconds
        - `direction`: Call direction (inbound/outbound)
        - `status`: Call outcome (optional)
        - `appointment_datetime`: When appointment scheduled (if status is terminvereinbart)
        
        **✅ Business Logic**:
        - When status is 'terminvereinbart', appointment_datetime is required
        - When status is not 'terminvereinbart', appointment_datetime must be empty
        """,
        request=CallLogSerializer,
        responses={
            201: OpenApiResponse(
                response=CallLogSerializer,
                description="✅ Call log created successfully"
            ),
            400: OpenApiResponse(description="❌ Validation error - Check call log data"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required for call log creation")
        },
        tags=["Call Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get call log details",
        description="""
        Retrieve detailed information about a specific call log.
        
        **🔐 Permission Requirements**: All authenticated users can view call details
        
        **📊 Detailed Information**:
        - Complete call record with all metadata
        - Lead information and context
        - Agent and workspace information
        - Call quality and outcome details
        - Appointment scheduling information
        """,
        responses={
            200: OpenApiResponse(response=CallLogSerializer, description="✅ Call log details retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Call log not found")
        },
        tags=["Call Management"]
    ),
    update=extend_schema(
        summary="✏️ Update call log",
        description="""
        Update call log information (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify call logs
        - **✅ Staff Members**: Can update call log details
        - **✅ Superusers**: Can update call log details
        
        **📝 Data Correction**:
        - Fix incorrect call data
        - Update missing information
        - Correct system integration errors
        - Update call status and appointments
        
        **⚠️ Data Integrity**:
        - Maintains call history accuracy
        - Ensures reporting consistency
        - Tracks modification history
        - Validates appointment logic
        """,
        request=CallLogSerializer,
        responses={
            200: OpenApiResponse(response=CallLogSerializer, description="✅ Call log updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Call log not found")
        },
        tags=["Call Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update call log",
        description="""
        Update specific fields of a call log (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=CallLogSerializer,
        responses={
            200: OpenApiResponse(response=CallLogSerializer, description="✅ Call log updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Call log not found")
        },
        tags=["Call Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete call log",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete a call log.**
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot delete call logs
        - **❌ Staff Members**: Cannot delete call logs
        - **✅ Superuser ONLY**: Can delete call logs
        
        **💥 Data Impact**:
        - Removes call record permanently
        - Affects reporting and analytics
        - May impact compliance requirements
        
        **🛡️ Compliance Considerations**:
        - Check legal requirements for call record retention
        - Ensure proper data backup before deletion
        - Consider data archival instead of deletion
        """,
        responses={
            204: OpenApiResponse(description="✅ Call log deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Only superusers can delete call logs",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        summary='Non-superuser attempted call log deletion',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 Call log not found")
        },
        tags=["Call Management"]
    ),
)
class CallLogViewSet(viewsets.ModelViewSet):
    """
    📱 **Call Log Management with Universal Read Access**
    
    Manages call logs with role-based write permissions:
    - **👤 All Users**: Can view all call logs (universal read access)
    - **👔 Staff**: Can create and modify call logs (data management)
    - **🔧 Superusers**: Can delete call logs (compliance/cleanup)
    """
    queryset = CallLog.objects.all()
    serializer_class = CallLogSerializer
    permission_classes = [CallLogPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CallLogFilter
    search_fields = [
        'lead__name', 'lead__surname', 'from_number', 'to_number', 
        'disconnection_reason', 'agent__workspace__workspace_name', 'status'
    ]
    ordering_fields = ['timestamp', 'duration', 'direction', 'status', 'appointment_datetime']
    ordering = ['-timestamp']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CallLogCreateSerializer
        return CallLogSerializer
    
    @extend_schema(
        summary="📊 Get call analytics",
        description="""
        Retrieve comprehensive call analytics and performance metrics.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view call analytics
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **📈 Analytics Included**:
        - Call volume and frequency trends
        - Duration analysis and averages
        - Success/failure rates and patterns
        - Direction breakdown (inbound vs outbound)
        - Performance metrics and KPIs
        - **NEW**: Status breakdown analytics
        - **NEW**: Appointment scheduling metrics
        
        **🎯 Business Intelligence**:
        - Agent performance evaluation
        - System efficiency metrics
        - Lead conversion correlation
        - Operational insights and trends
        """,
        responses={
            200: OpenApiResponse(
                response=CallLogAnalyticsSerializer,
                description="✅ Call analytics retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Call Analytics',
                        summary='Comprehensive call metrics with new status data',
                        value={
                            'total_calls': 2500,
                            'calls_today': 45,
                            'calls_this_week': 280,
                            'calls_this_month': 1150,
                            'avg_duration': 165.5,
                            'total_duration': 413750,
                            'inbound_calls': 850,
                            'outbound_calls': 1650,
                            'status_breakdown': {
                                'terminvereinbart': 450,
                                'erreicht': 800,
                                'nicht erreicht': 900,
                                'kein interesse': 350
                            },
                            'appointments_scheduled': 450,
                            'appointments_today': 12
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def analytics(self, request):
        """Get comprehensive call analytics"""
        from django.db.models import Count, Avg, Sum
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Basic call statistics
        total_calls = CallLog.objects.count()
        calls_today = CallLog.objects.filter(timestamp__date=today).count()
        calls_this_week = CallLog.objects.filter(timestamp__gte=week_ago).count()
        calls_this_month = CallLog.objects.filter(timestamp__gte=month_ago).count()
        
        # Duration analytics
        duration_stats = CallLog.objects.aggregate(
            avg_duration=Avg('duration'),
            total_duration=Sum('duration')
        )
        
        # Direction breakdown
        direction_stats = CallLog.objects.values('direction').annotate(
            count=Count('id')
        )
        
        # Status breakdown
        status_stats = CallLog.objects.filter(status__isnull=False).values('status').annotate(
            count=Count('id')
        )
        status_breakdown = {item['status']: item['count'] for item in status_stats}
        
        # Appointment statistics
        appointments_scheduled = CallLog.objects.filter(appointment_datetime__isnull=False).count()
        appointments_today = CallLog.objects.filter(appointment_datetime__date=today).count()
        
        analytics_data = {
            'total_calls': total_calls,
            'calls_today': calls_today,
            'calls_this_week': calls_this_week,
            'calls_this_month': calls_this_month,
            'avg_duration': duration_stats['avg_duration'] or 0,
            'total_duration': duration_stats['total_duration'] or 0,
            'inbound_calls': next((item['count'] for item in direction_stats if item['direction'] == 'inbound'), 0),
            'outbound_calls': next((item['count'] for item in direction_stats if item['direction'] == 'outbound'), 0),
            'status_breakdown': status_breakdown,
            'appointments_scheduled': appointments_scheduled,
            'appointments_today': appointments_today,
        }
        
        return Response(analytics_data)
    
    @extend_schema(
        summary="📊 Get call status analytics",
        description="""
        Retrieve call status breakdown and success rate analytics.
        
        **🔐 Permission Requirements**: All authenticated users can access
        
        **📈 Status Analytics**:
        - Breakdown by German status choices
        - Success rate calculations
        - Status trends and patterns
        """,
        responses={
            200: OpenApiResponse(
                response=CallLogStatusAnalyticsSerializer,
                description="✅ Status analytics retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def status_analytics(self, request):
        """Get call status breakdown analytics"""
        total_calls = CallLog.objects.count()
        
        # Status breakdown
        status_stats = CallLog.objects.filter(status__isnull=False).values('status').annotate(
            count=Count('id')
        )
        status_breakdown = {item['status']: item['count'] for item in status_stats}
        
        # Calculate success rate (reached + appointment_scheduled)
        successful_calls = status_breakdown.get('reached', 0) + status_breakdown.get('appointment_scheduled', 0)
        success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
        
        return Response({
            'total_calls': total_calls,
            'status_breakdown': status_breakdown,
            'success_rate': round(success_rate, 2)
        })
    
    @extend_schema(
        summary="👤 Get agent performance analytics",
        description="""
        Retrieve performance metrics broken down by agent.
        
        **🔐 Permission Requirements**: All authenticated users can access
        
        **📊 Agent Metrics**:
        - Calls per agent
        - Duration averages by agent
        - Status breakdown per agent
        - Appointment scheduling rates
        """,
        responses={
            200: OpenApiResponse(
                response=CallLogAgentPerformanceSerializer,
                description="✅ Agent performance data retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def agent_performance(self, request):
        """Get agent performance analytics"""
        from django.db.models import Avg, Count
        
        # Group by agent and get performance metrics
        agent_stats = CallLog.objects.values(
            'agent__agent_id', 'agent__workspace__workspace_name'
        ).annotate(
            total_calls=Count('id'),
            avg_duration=Avg('duration'),
            appointments_scheduled=Count('id', filter=Q(appointment_datetime__isnull=False))
        ).order_by('-total_calls')
        
        performance_data = []
        for stat in agent_stats:
            # Get status breakdown for this agent
            agent_status_stats = CallLog.objects.filter(
                agent__agent_id=stat['agent__agent_id']
            ).filter(status__isnull=False).values('status').annotate(count=Count('id'))
            
            status_breakdown = {item['status']: item['count'] for item in agent_status_stats}
            
            performance_data.append({
                'agent_id': stat['agent__agent_id'],
                'agent_workspace': stat['agent__workspace__workspace_name'],
                'total_calls': stat['total_calls'],
                'avg_duration': round(stat['avg_duration'] or 0, 1),
                'status_breakdown': status_breakdown,
                'appointments_scheduled': stat['appointments_scheduled']
            })
        
        # Return the aggregated performance data
        return Response(performance_data)

    @extend_schema(
        summary="📞 Make outbound call",
        description="""
        Initiate an outbound call using LiveKit with specified agent.
        
        **⚡ SYNCHRONOUS ENDPOINT - NOT ASYNC!**
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can make calls with their agents
        - **✅ Staff/Superuser**: Can use any agent
        
        **📋 Required Information**:
        - `phone`: Phone number to call (required)
        - `agent_id`: Agent UUID to make the call (required)
        - `lead_id`: Lead UUID to associate with call (optional)
        
        **📞 Call Process**:
        1. Validates agent belongs to user's workspace
        2. Retrieves lead information if provided
        3. Dispatches agent to LiveKit room
        4. Initiates SIP call to the phone number
        5. Creates call log entry
        
        **🎯 Use Cases**:
        - Direct outbound calls
        - Sales outreach
        - Customer follow-up
        - Support calls
        """,
        request=OutboundCallSerializer,
        responses={
            200: OpenApiResponse(
                description="✅ Call initiated successfully",
                examples=[
                    OpenApiExample(
                        'Successful Call Initiation',
                        summary='Call started successfully',
                        value={
                            'success': True,
                            'room_name': 'outbound-call-abc123',
                            'participant_id': 'PA_abc123',
                            'dispatch_id': 'DP_xyz789',
                            'sip_call_id': 'SIP_123456',
                            'to_number': '+4915111857588',
                            'agent_name': 'Sales Agent',
                            'call_log_id': 'uuid-of-created-log'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="❌ Validation error",
                examples=[
                    OpenApiExample(
                        'Agent Not Found',
                        value={'agent_id': ['Agent not found']}
                    ),
                    OpenApiExample(
                        'Workspace Access Denied',
                        value={'agent_id': ['You can only use agents from your own workspace']}
                    ),
                    OpenApiExample(
                        'Invalid Phone',
                        value={'phone': ['Phone number must start with + and country code']}
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            500: OpenApiResponse(
                description="❌ Call initiation failed",
                examples=[
                    OpenApiExample(
                        'LiveKit Error',
                        value={
                            'success': False,
                            'error': 'Failed to connect to SIP trunk',
                            'to_number': '+4915111857588',
                            'agent_name': 'Sales Agent'
                        }
                    )
                ]
            )
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['post'])
    def make_outbound_call(self, request):
        """
        Make an outbound call - SYNCHRONOUS ENDPOINT (NOT ASYNC!)
        
        This endpoint triggers the LiveKit outbound call process synchronously.
        It uses the make_outbound_call_sync function which internally handles async operations.
        """
        serializer = OutboundCallSerializer(data=request.data, context={'request': request})
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get validated data
        validated_data = serializer.validated_data
        
        # Fixed SIP trunk ID
        SIP_TRUNK_ID = "ST_F5KZ4yNHBegK"
        
        # Retrieve agent
        try:
            agent = Agent.objects.select_related('workspace', 'voice').get(
                agent_id=validated_data['agent_id']
            )
        except Agent.DoesNotExist:
            return Response(
                {'error': 'Agent not found'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Retrieve lead if provided
        lead = None
        lead_data = {
            "name": "",
            "surname": "",
            "email": "",
            "phone": validated_data['phone'],
            "meta_data": {}
        }
        
        if validated_data.get('lead_id'):
            try:
                lead = Lead.objects.get(id=validated_data['lead_id'])
                lead_data = {
                    "name": lead.name,
                    "surname": lead.surname or "",
                    "email": lead.email,
                    "phone": lead.phone,
                    "meta_data": lead.meta_data or {}
                }
            except Lead.DoesNotExist:
                # Lead not found, but we continue with phone only
                pass
        
        # Prepare agent configuration dictionary
        agent_config = {
            "workspace": str(agent.workspace.id),
            "name": agent.name,
            "status": agent.status,
            "greeting_inbound": agent.greeting_inbound,
            "greeting_outbound": agent.greeting_outbound,
            "voice": str(agent.voice.voice_external_id) if agent.voice else "",
            "language": agent.language,
            "retry_interval": agent.retry_interval,
            "max_retries": agent.max_retries,
            "workdays": agent.workdays,
            "call_from": str(agent.call_from),
            "call_to": str(agent.call_to),
            "character": agent.character,
            "prompt": agent.prompt,
            "config_id": agent.config_id or "",
            "calendar_configuration": str(agent.calendar_configuration.id) if agent.calendar_configuration else ""
        }
        
        # Import the SYNC function (NOT ASYNC!)
        try:
            from core.utils.livekit_calls import make_outbound_call_sync
        except ImportError:
            return Response(
                {'error': 'LiveKit integration not available'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Make the outbound call using SYNC wrapper
        # THIS IS NOT ASYNC - IT'S A SYNCHRONOUS CALL!
        result = make_outbound_call_sync(
            sip_trunk_id=SIP_TRUNK_ID,
            agent_config=agent_config,
            lead_data=lead_data,
            from_number="",  # Not used anymore
            campaign_id="",  # Not used anymore
            call_reason=None  # Not used anymore
        )
        
        # Create call log entry if successful
        if result.get('success'):
            with transaction.atomic():
                call_log = CallLog.objects.create(
                    lead=lead,  # Can be None if no lead_id provided
                    agent=agent,
                    from_number="",
                    to_number=validated_data['phone'],
                    duration=0,  # Will be updated when call ends
                    direction='outbound',
                    status='reached',  # Initial status
                    disconnection_reason='ongoing'  # Call is ongoing
                )
                result['call_log_id'] = str(call_log.id)
        
        # Return the result
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @extend_schema(
        summary="📅 Get appointment statistics",
        description="""
        Retrieve comprehensive appointment scheduling statistics.
        
        **🔐 Permission Requirements**: All authenticated users can access
        
        **📊 Appointment Metrics**:
        - Total appointments scheduled
        - Appointments by time period
        - Upcoming vs past appointments
        - Appointment trends
        """,
        responses={
            200: OpenApiResponse(
                response=CallLogAppointmentStatsSerializer,
                description="✅ Appointment statistics retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def appointment_stats(self, request):
        """Get appointment scheduling statistics"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Total appointments
        total_appointments = CallLog.objects.filter(appointment_datetime__isnull=False).count()
        
        # Appointments by time period
        appointments_today = CallLog.objects.filter(appointment_datetime__date=today).count()
        appointments_this_week = CallLog.objects.filter(appointment_datetime__gte=week_ago).count()
        appointments_this_month = CallLog.objects.filter(appointment_datetime__gte=month_ago).count()
        
        # Upcoming vs past appointments
        upcoming_appointments = CallLog.objects.filter(appointment_datetime__gte=now).count()
        past_appointments = CallLog.objects.filter(appointment_datetime__lt=now).count()
        
        return Response({
            'total_appointments': total_appointments,
            'appointments_today': appointments_today,
            'appointments_this_week': appointments_this_week,
            'appointments_this_month': appointments_this_month,
            'upcoming_appointments': upcoming_appointments,
            'past_appointments': past_appointments
        })
    
    @extend_schema(
        summary="📅 Get daily call statistics",
        description="""
        Retrieve call statistics broken down by day for a specified period.
        
        **🔐 Permission Requirements**: All authenticated users can access
        
        **📊 Daily Breakdown**:
        - Calls per day over specified period
        - Duration trends and patterns
        - Success rates by day
        - Workday vs weekend patterns
        
        **🔍 Query Parameters**:
        - `days`: Number of days to include (default: 30)
        - Automatically calculates from current date backwards
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Daily call statistics retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Daily Statistics',
                        summary='Call activity by day',
                        value={
                            'period_days': 7,
                            'daily_stats': [
                                {'date': '2024-01-15', 'calls': 45, 'avg_duration': 180, 'total_duration': 8100},
                                {'date': '2024-01-14', 'calls': 52, 'avg_duration': 165, 'total_duration': 8580},
                                {'date': '2024-01-13', 'calls': 38, 'avg_duration': 195, 'total_duration': 7410}
                            ],
                            'totals': {'calls': 380, 'avg_duration': 175, 'total_duration': 66500}
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def daily_stats(self, request):
        """Get daily call statistics"""
        from django.db.models import Count, Avg, Sum
        from django.utils import timezone
        from datetime import timedelta, date
        
        # Get number of days from query parameter (default: 30)
        days = int(request.query_params.get('days', 30))
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days-1)
        
        # Get daily statistics
        daily_stats = []
        current_date = start_date
        
        while current_date <= end_date:
            day_calls = CallLog.objects.filter(timestamp__date=current_date)
            stats = day_calls.aggregate(
                call_count=Count('id'),
                avg_duration=Avg('duration'),
                total_duration=Sum('duration')
            )
            
            daily_stats.append({
                'date': current_date.isoformat(),
                'calls': stats['call_count'] or 0,
                'avg_duration': round(stats['avg_duration'] or 0, 1),
                'total_duration': stats['total_duration'] or 0
            })
            
            current_date += timedelta(days=1)
        
        # Calculate totals
        total_calls = sum(day['calls'] for day in daily_stats)
        total_duration = sum(day['total_duration'] for day in daily_stats)
        avg_duration = total_duration / total_calls if total_calls > 0 else 0
        
        return Response({
            'period_days': days,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'daily_stats': daily_stats,
            'totals': {
                'calls': total_calls,
                'avg_duration': round(avg_duration, 1),
                'total_duration': total_duration
            }
        })
    
    @extend_schema(
        summary="⏱️ Get call duration distribution",
        description="""
        Analyze call duration patterns and distribution across different time ranges.
        
        **🔐 Permission Requirements**: All authenticated users can access
        
        **📊 Duration Analysis**:
        - Calls grouped by duration ranges
        - Short, medium, and long call distribution
        - Duration percentiles and statistics
        - Pattern identification for call quality
        
        **🎯 Use Cases**:
        - Call quality assessment
        - Agent performance evaluation
        - System optimization insights
        - Customer engagement analysis
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Call duration distribution retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Duration Distribution',
                        summary='Call length patterns',
                        value={
                            'total_calls': 2500,
                            'duration_ranges': {
                                '0-30s': {'count': 450, 'percentage': 18.0},
                                '31-60s': {'count': 520, 'percentage': 20.8},
                                '61-120s': {'count': 680, 'percentage': 27.2},
                                '121-300s': {'count': 580, 'percentage': 23.2},
                                '300s+': {'count': 270, 'percentage': 10.8}
                            },
                            'statistics': {
                                'avg_duration': 165.5,
                                'median_duration': 145,
                                'min_duration': 5,
                                'max_duration': 1250
                            }
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def duration_distribution(self, request):
        """Get call duration distribution analysis"""
        from django.db.models import Count, Q
        
        total_calls = CallLog.objects.count()
        
        if total_calls == 0:
            return Response({
                'total_calls': 0,
                'duration_ranges': {},
                'statistics': {}
            })
        
        # Define duration ranges
        ranges = [
            ('0-30s', Q(duration__lte=30)),
            ('31-60s', Q(duration__gt=30, duration__lte=60)),
            ('61-120s', Q(duration__gt=60, duration__lte=120)),
            ('121-300s', Q(duration__gt=120, duration__lte=300)),
            ('300s+', Q(duration__gt=300))
        ]
        
        duration_ranges = {}
        for range_name, range_filter in ranges:
            count = CallLog.objects.filter(range_filter).count()
            percentage = (count / total_calls) * 100 if total_calls > 0 else 0
            duration_ranges[range_name] = {
                'count': count,
                'percentage': round(percentage, 1)
            }
        
        # Basic statistics
        from django.db.models import Avg, Min, Max
        stats = CallLog.objects.aggregate(
            avg_duration=Avg('duration'),
            min_duration=Min('duration'),
            max_duration=Max('duration')
        )
        
        return Response({
            'total_calls': total_calls,
            'duration_ranges': duration_ranges,
            'statistics': {
                'avg_duration': round(stats['avg_duration'] or 0, 1),
                'min_duration': stats['min_duration'] or 0,
                'max_duration': stats['max_duration'] or 0
            }
        }) 