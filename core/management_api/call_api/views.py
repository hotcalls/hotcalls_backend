from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample, OpenApiParameter
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied
import json
import os
import logging

logger = logging.getLogger(__name__)

from core.models import CallLog, Agent, Lead, CallTask, CallStatus
from .serializers import (
    CallLogSerializer, CallLogCreateSerializer, CallLogAnalyticsSerializer, 
    CallLogStatusAnalyticsSerializer, CallLogAgentPerformanceSerializer,
    CallLogAppointmentStatsSerializer, OutboundCallSerializer, 
    TestCallSerializer, CallTaskSerializer, CallTaskTriggerSerializer
)
from .filters import CallLogFilter, CallTaskFilter
from .permissions import CallLogPermission, CallLogAnalyticsPermission, CallTaskPermission


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
        tags=["Agent Management"]
    ),
    create=extend_schema(
        summary="➕ Create call log",
        description="""
        Create a new call log entry using LiveKit secret authentication.
        
        **🔐 Authentication Required**:
        - **Header:** `X-LiveKit-Token: <your-generated-token>`
        - **No Django Token needed** - only the LiveKit agent token header
        
        **📱 System Integration**:
        - Designed for external call systems
        - Automatic call log creation from LiveKit
        - No user authentication required
        
        **📝 Required Information**:
        - `lead`: Associated lead ID (UUID)
        - `agent`: Agent who made/received the call (UUID)
        - `from_number`, `to_number`: Phone numbers involved
        - `duration`: Call duration in seconds
        - `direction`: Call direction (inbound/outbound)
        - `status`: Call outcome (optional)
        - `appointment_datetime`: When appointment scheduled (if status is appointment_scheduled)
        
        **✅ Business Logic**:
        - When status is 'appointment_scheduled', appointment_datetime is required
        - When status is not 'appointment_scheduled', appointment_datetime must be empty
        """,
        parameters=[
            OpenApiParameter(
                name='X-LiveKit-Token',
                location=OpenApiParameter.HEADER,
                description='LiveKit agent token for authentication (generated via /api/livekit/tokens/generate_token/)',
                required=True,
                type=str
            )
        ],
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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
    
    def perform_create(self, serializer):
        """Create call log and record actual call minutes usage"""
        from core.quotas import enforce_and_record
        from decimal import Decimal
        
        # Create the call log first
        call_log = serializer.save()
        
        # Record actual call duration in quota system
        try:
            # Get workspace from agent
            workspace = call_log.agent.workspace
            
            # Convert duration from seconds to minutes
            duration_minutes = Decimal(call_log.duration) / Decimal('60')
            
            # Record actual usage (virtual route, bypasses HTTP middleware)
            enforce_and_record(
                workspace=workspace,
                route_name="internal:call_duration_used",
                http_method="POST",
                amount=duration_minutes
            )
            
            logger.info(f"📞 Recorded {duration_minutes} minutes usage for workspace {workspace.id}")
            
        except Exception as quota_err:
            # Log error but don't fail call log creation
            logger.error(f"⚠️ Failed to record call minutes for call log {call_log.id}: {quota_err}")
            # Call log creation succeeds regardless of quota recording errors
        
        # Trigger CallTask feedback loop (async, non-blocking)
        try:
            from core.tasks import update_calltask_from_calllog
            update_calltask_from_calllog.delay(str(call_log.id))
            logger.info(f"🔄 Triggered CallTask feedback for CallLog {call_log.id}")
            
        except Exception as feedback_err:
            # Log error but don't fail call log creation
            logger.error(f"⚠️ Failed to trigger CallTask feedback for call log {call_log.id}: {feedback_err}")
            # Call log creation succeeds regardless of feedback trigger errors
    
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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

    def _prepare_lead_data(self, validated_data):
        """
        Prepare lead data from either database or request data
        Supports flexible lead data with custom fields
        """
        # Start with basic structure
        lead_data = {
            "name": "",
            "surname": "",
            "email": "",
            "phone": validated_data['phone'],  # Always use provided phone as fallback
            "lead_source": "",
            "campaign_id": "",
            "meta_data": {}
        }
        
        # If lead_id provided, load from database first
        if validated_data.get('lead_id'):
            try:
                lead = Lead.objects.get(id=validated_data['lead_id'])
                lead_data.update({
                    "name": lead.name,
                    "surname": lead.surname or "",
                    "email": lead.email,
                    "phone": lead.phone,
                    "lead_source": getattr(lead, 'lead_source', ''),
                    "campaign_id": getattr(lead, 'campaign_id', ''),
                    "meta_data": lead.meta_data or {}
                })
            except Lead.DoesNotExist:
                # Lead not found, continue with defaults
                pass
        
        # Override/supplement with lead_data from request
        if validated_data.get('lead_data'):
            request_lead_data = validated_data['lead_data']
            
            # Update basic fields
            for field in ['name', 'surname', 'email', 'phone', 'lead_source', 'campaign_id']:
                if field in request_lead_data:
                    lead_data[field] = request_lead_data[field]
            
            # Handle custom fields
            if 'custom_fields' in request_lead_data:
                # Merge custom fields into meta_data
                lead_data['meta_data'].update(request_lead_data['custom_fields'])
            
            # Also merge any other fields from request
            for key, value in request_lead_data.items():
                if key not in lead_data and key != 'custom_fields':
                    lead_data[key] = value
        
        return lead_data
    
    def _process_greeting_template(self, template, lead_data):
        """
        Process greeting template with placeholders
        Replaces {placeholder} with actual values from lead_data
        """
        import re
        
        # Collect all available data for replacement
        available_data = {}
        
        # Add basic lead fields
        available_data.update(lead_data)
        
        # Add meta_data fields at top level for easy access
        if 'meta_data' in lead_data:
            available_data.update(lead_data['meta_data'])
        
        # Add custom_fields if present (for backwards compatibility)
        if 'custom_fields' in lead_data:
            available_data.update(lead_data['custom_fields'])
        
        # Replace {placeholder} with actual values
        def replace_placeholder(match):
            key = match.group(1)
            # Return empty string if key not found (don't break the greeting)
            return str(available_data.get(key, ''))
        
        # Use regex to find and replace all {word} patterns
        processed_template = re.sub(r'\{(\w+)\}', replace_placeholder, template)
        
        return processed_template
    
    def _merge_agent_config(self, base_agent, override_config):
        """
        Merge agent configuration with overrides
        Base agent data from DB, selectively override with provided config
        """
        # Build base configuration from database agent
        agent_config = {
            "workspace": str(base_agent.workspace.id),
            "name": base_agent.name,
            "status": base_agent.status,
            "greeting_inbound": base_agent.greeting_inbound,
            "greeting_outbound": base_agent.greeting_outbound,
            "voice": str(base_agent.voice.voice_external_id) if base_agent.voice else "",
            "language": base_agent.language,
            "retry_interval": base_agent.retry_interval,
            "max_retries": base_agent.max_retries,
            "workdays": base_agent.workdays,
            "call_from": str(base_agent.call_from) if base_agent.call_from else "",
            "call_to": str(base_agent.call_to) if base_agent.call_to else "",
            "character": base_agent.character,
            "prompt": base_agent.prompt,
            "config_id": base_agent.config_id or "",
            "calendar_configuration": str(base_agent.calendar_configuration.id) if base_agent.calendar_configuration else ""
        }
        
        # Apply overrides if provided
        if override_config:
            for key, value in override_config.items():
                if value is not None:  # Allow explicit None to clear values
                    # Special handling for voice - might be voice UUID or external ID
                    if key == 'voice' and value:
                        # Try to find voice and get external ID
                        try:
                            from core.models import Voice
                            if len(str(value)) == 36:  # Looks like UUID
                                voice = Voice.objects.get(id=value)
                                agent_config['voice'] = str(voice.voice_external_id)
                            else:
                                # Assume it's already an external ID
                                agent_config['voice'] = str(value)
                        except (Voice.DoesNotExist, ValueError):
                            # Keep original if voice not found
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Voice override failed: {value}")
                    else:
                        # Direct override for other fields
                        agent_config[key] = value
        
        return agent_config

    # Removed synchronous make_outbound_call endpoint
    
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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
        tags=["Agent Management"]
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


@extend_schema_view(
    list=extend_schema(
        summary="📋 List call tasks",
        description="""
        Retrieve all call tasks with filtering and search capabilities.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view call tasks from their workspaces
        - **✅ Superusers**: Can view all call tasks
        
        **📊 Call Task Management**:
        - View scheduled calls and their status
        - Track retry attempts and progress
        - Monitor call queue and execution
        """,
        responses={
            200: OpenApiResponse(
                response=CallTaskSerializer(many=True),
                description="✅ Successfully retrieved call tasks"
            ),
            401: OpenApiResponse(description="🚫 Authentication required")
        },
        tags=["Call Management"]
    ),
    create=extend_schema(
        summary="➕ Create call task",
        description="""
        Create a new call task for scheduling.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can create tasks for their workspaces
        - **✅ Superusers**: Can create tasks for any workspace
        """,
        request=CallTaskSerializer,
        responses={
            201: OpenApiResponse(response=CallTaskSerializer, description="✅ Call task created successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied")
        },
        tags=["Call Management"]
    ),
)
class CallTaskViewSet(viewsets.ModelViewSet):
    """ViewSet for managing call tasks"""
    serializer_class = CallTaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CallTaskFilter
    search_fields = ['lead__name', 'agent__name', 'workspace__workspace_name', 'phone']
    ordering_fields = ['created_at', 'next_call', 'status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        
        if user.is_superuser:
            # Superusers can see all call tasks
            return CallTask.objects.all()
        else:
            # Regular users can only see call tasks from their workspaces
            user_workspaces = user.mapping_user_workspaces.all()
            return CallTask.objects.filter(workspace__in=user_workspaces)
    
    def get_permissions(self):
        """Assign permissions based on the action"""
        if self.action in ['create', 'list', 'retrieve']:
            # All authenticated users can create, list and view call tasks
            permission_classes = [permissions.IsAuthenticated]
        else:
            # Only superusers can update, delete and trigger
            permission_classes = [permissions.IsAdminUser]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """Ensure user can only create call tasks for their workspaces"""
        user = self.request.user
        workspace = serializer.validated_data.get('workspace')
        
        # Validate workspace access for non-superusers
        if not user.is_superuser and workspace not in user.mapping_user_workspaces.all():
            raise PermissionDenied("You can only create call tasks for your workspaces")
        
        # Set next_call to immediate (now) for all new call tasks
        serializer.save(next_call=timezone.now())
    
    @extend_schema(
        summary="🚀 Trigger a call manually",
        description="""
        Manually trigger a call for a specific CallTask.
        
        **🔐 Permission Requirements**:
        - **🔴 Superuser Only**: Only superusers can trigger calls manually
        
        **📋 Prerequisites**:
        - CallTask must exist
        - CallTask status should be SCHEDULED or RETRY
        
        **🎯 What happens**:
        - Initiates the call immediately
        - Updates CallTask status to IN_PROGRESS
        - Call will be processed by the call system
        """,
        request=None,
        responses={
            200: OpenApiResponse(
                response=CallTaskTriggerSerializer,
                description="Call triggered successfully"
            ),
            400: OpenApiResponse(description="Invalid task status"),
            403: OpenApiResponse(description="Superuser required"),
            404: OpenApiResponse(description="CallTask not found")
        },
        tags=["Call Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def trigger(self, request, pk=None):
        """Manually trigger a call for a specific CallTask"""
        try:
            call_task = self.get_object()
            
            # Check if task is in a valid state to be triggered
            if call_task.status not in [CallStatus.SCHEDULED, CallStatus.RETRY]:
                return Response(
                    {'error': f'Cannot trigger task with status: {call_task.status}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update status to in progress
            call_task.status = CallStatus.IN_PROGRESS
            call_task.save(update_fields=['status'])
            
            return Response({
                'task_id': str(call_task.id),
                'status': call_task.status,
                'message': 'Call task triggered successfully'
            }, status=status.HTTP_200_OK)
            
        except CallTask.DoesNotExist:
            return Response(
                {'error': 'CallTask not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )


@extend_schema(
    summary="📞 Make test call",
    description="""
    Create a test call task that will call the authenticated user's phone number.
    
    **🔐 Permission Requirements**:
    - **✅ All Authenticated Users**: Can make test calls with their agents
    
    **📱 Requirements**:
    - User must have a phone number in their profile
    - Agent must belong to user's workspace (unless superuser)
    
    **🎯 What happens**:
    - Creates a CallTask entry with user's phone number
    - Sets status to SCHEDULED for immediate execution
    - Call will be processed by Celery task system
    """,
    request=TestCallSerializer,
    responses={
        201: OpenApiResponse(
            description="✅ Test call task created successfully",
            examples=[
                {
                    'success': True,
                    'call_task_id': '550e8400-e29b-41d4-a716-446655440000'
                }
            ]
        ),
        400: OpenApiResponse(description="❌ Validation error or missing phone number"),
        401: OpenApiResponse(description="🚫 Authentication required"),
        403: OpenApiResponse(description="🚫 No access to specified agent")
    },
    tags=["Call Management"]
)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def make_test_call(request):
    """
    Create a test call task - ONLY creates CallTask entry!
    
    The actual call will be handled by Celery tasks.
    Requires agent_id and authentication token.
    """
    serializer = TestCallSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Get validated data
    validated_data = serializer.validated_data
    user = request.user
    
    # Use the authenticated user's phone number for test call
    user_phone = user.phone
    if not user_phone:
        return Response(
            {'error': 'User phone number not found. Please update your profile with a phone number.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Retrieve agent and check permissions
    try:
        agent = Agent.objects.select_related('workspace', 'voice').get(
            agent_id=validated_data['agent_id']
        )
        
        # Check if user has access to this agent's workspace
        if not user.is_superuser and agent.workspace not in user.mapping_user_workspaces.all():
            return Response(
                {'error': 'You do not have access to this agent'}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
    except Agent.DoesNotExist:
        return Response(
            {'error': 'Agent not found'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create CallTask entry - that's it!
    call_task = CallTask.objects.create(
        status=CallStatus.SCHEDULED,
        attempts=0,
        phone=user_phone,
        workspace=agent.workspace,
        lead=None,  # null=True for test calls
        agent=agent,
        next_call=timezone.now()  # immediate execution
    )
    
    # Return success response
    return Response({
        'success': True,
        'call_task_id': str(call_task.id)
    }, status=status.HTTP_201_CREATED)

 