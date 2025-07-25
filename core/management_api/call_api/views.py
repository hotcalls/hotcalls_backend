from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.models import CallLog
from .serializers import CallLogSerializer, CallLogCreateSerializer, CallLogAnalyticsSerializer
from .filters import CallLogFilter
from .permissions import CallLogPermission, CallLogAnalyticsPermission


@extend_schema_view(
    list=extend_schema(
        summary="List call logs",
        description="Retrieve a list of all call logs with filtering and search capabilities",
        tags=["Call Management"]
    ),
    create=extend_schema(
        summary="Create a new call log",
        description="Create a new call log entry (staff only)",
        tags=["Call Management"]
    ),
    retrieve=extend_schema(
        summary="Get call log details",
        description="Retrieve detailed information about a specific call log",
        tags=["Call Management"]
    ),
    update=extend_schema(
        summary="Update call log",
        description="Update all fields of a call log (staff only)",
        tags=["Call Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update call log",
        description="Update specific fields of a call log (staff only)",
        tags=["Call Management"]
    ),
    destroy=extend_schema(
        summary="Delete call log",
        description="Delete a call log (superuser only)",
        tags=["Call Management"]
    ),
)
class CallLogViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CallLog model operations
    
    Provides CRUD operations for call logs:
    - All users can view call logs
    - Staff can create/modify call logs
    - Superusers can delete call logs
    """
    queryset = CallLog.objects.all()
    permission_classes = [CallLogPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CallLogFilter
    search_fields = ['from_number', 'to_number', 'lead__name', 'lead__email', 'disconnection_reason']
    ordering_fields = ['timestamp', 'duration', 'direction']
    ordering = ['-timestamp']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return CallLogCreateSerializer
        return CallLogSerializer
    
    @extend_schema(
        summary="Get call analytics",
        description="Get analytics and statistics about calls",
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[CallLogAnalyticsPermission])
    def analytics(self, request):
        """Get call analytics"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Basic statistics
        total_calls = queryset.count()
        total_duration = queryset.aggregate(Sum('duration'))['duration__sum'] or 0
        average_duration = queryset.aggregate(Avg('duration'))['duration__avg'] or 0
        
        # Direction statistics
        inbound_calls = queryset.filter(direction='inbound').count()
        outbound_calls = queryset.filter(direction='outbound').count()
        
        # Success/failure statistics
        successful_calls = queryset.filter(duration__gt=0).count()
        failed_calls = total_calls - successful_calls
        
        analytics_data = {
            'total_calls': total_calls,
            'total_duration': total_duration,
            'average_duration': round(average_duration, 2),
            'inbound_calls': inbound_calls,
            'outbound_calls': outbound_calls,
            'successful_calls': successful_calls,
            'failed_calls': failed_calls,
        }
        
        serializer = CallLogAnalyticsSerializer(analytics_data)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Get daily call statistics",
        description="Get call statistics grouped by day",
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'])
    def daily_stats(self, request):
        """Get daily call statistics"""
        from django.db.models.functions import TruncDate
        
        queryset = self.filter_queryset(self.get_queryset())
        
        daily_stats = queryset.extra(
            select={'day': 'date(timestamp)'}
        ).values('day').annotate(
            call_count=Count('id'),
            total_duration=Sum('duration'),
            average_duration=Avg('duration'),
            successful_calls=Count('id', filter=Q(duration__gt=0)),
            failed_calls=Count('id', filter=Q(duration=0))
        ).order_by('-day')
        
        return Response(list(daily_stats))
    
    @extend_schema(
        summary="Get call duration distribution",
        description="Get distribution of call durations",
        tags=["Call Management"]
    )
    @action(detail=False, methods=['get'])
    def duration_distribution(self, request):
        """Get call duration distribution"""
        queryset = self.filter_queryset(self.get_queryset())
        
        distribution = {
            'under_30s': queryset.filter(duration__lt=30).count(),
            '30s_to_1m': queryset.filter(duration__gte=30, duration__lt=60).count(),
            '1m_to_3m': queryset.filter(duration__gte=60, duration__lt=180).count(),
            '3m_to_5m': queryset.filter(duration__gte=180, duration__lt=300).count(),
            '5m_to_10m': queryset.filter(duration__gte=300, duration__lt=600).count(),
            'over_10m': queryset.filter(duration__gte=600).count(),
        }
        
        return Response(distribution) 