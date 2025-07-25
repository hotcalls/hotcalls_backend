from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.models import Lead
from .serializers import (
    LeadSerializer, LeadCreateSerializer, LeadUpdateSerializer,
    LeadBulkCreateSerializer, LeadMetaDataUpdateSerializer
)
from .filters import LeadFilter
from .permissions import LeadPermission, LeadBulkPermission


@extend_schema_view(
    list=extend_schema(
        summary="List leads",
        description="Retrieve a list of all leads with filtering and search capabilities",
        tags=["Lead Management"]
    ),
    create=extend_schema(
        summary="Create a new lead",
        description="Create a new lead",
        tags=["Lead Management"]
    ),
    retrieve=extend_schema(
        summary="Get lead details",
        description="Retrieve detailed information about a specific lead",
        tags=["Lead Management"]
    ),
    update=extend_schema(
        summary="Update lead",
        description="Update all fields of a lead (staff only)",
        tags=["Lead Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update lead",
        description="Update specific fields of a lead (staff only)",
        tags=["Lead Management"]
    ),
    destroy=extend_schema(
        summary="Delete lead",
        description="Delete a lead (staff only)",
        tags=["Lead Management"]
    ),
)
class LeadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Lead model operations
    
    Provides CRUD operations for leads:
    - All users can view and create leads
    - Staff can modify and delete leads
    """
    queryset = Lead.objects.all()
    permission_classes = [LeadPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = LeadFilter
    search_fields = ['name', 'surname', 'email', 'phone']
    ordering_fields = ['name', 'surname', 'email', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return LeadCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LeadUpdateSerializer
        return LeadSerializer
    
    @extend_schema(
        summary="Bulk create leads",
        description="Create multiple leads at once",
        tags=["Lead Management"]
    )
    @action(detail=False, methods=['post'], permission_classes=[LeadBulkPermission])
    def bulk_create(self, request):
        """Bulk create leads"""
        serializer = LeadBulkCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            leads = serializer.save()
            return Response({
                'message': f'Successfully created {len(leads)} leads',
                'created_leads': [lead.id for lead in leads]
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Update lead metadata",
        description="Update the metadata of a lead",
        tags=["Lead Management"]
    )
    @action(detail=True, methods=['patch'], permission_classes=[LeadPermission])
    def update_metadata(self, request, pk=None):
        """Update lead metadata"""
        lead = self.get_object()
        serializer = LeadMetaDataUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            # Merge with existing metadata
            existing_metadata = lead.meta_data or {}
            new_metadata = serializer.validated_data['meta_data']
            existing_metadata.update(new_metadata)
            
            lead.meta_data = existing_metadata
            lead.save()
            
            return Response(LeadSerializer(lead).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Get lead call history",
        description="Get all call logs for this lead",
        tags=["Lead Management"]
    )
    @action(detail=True, methods=['get'])
    def call_history(self, request, pk=None):
        """Get call history for a lead"""
        lead = self.get_object()
        call_logs = lead.mapping_lead_calllogs.all().order_by('-timestamp')
        
        # Simple serialization for call logs
        call_data = []
        for call in call_logs:
            call_data.append({
                'id': call.id,
                'timestamp': call.timestamp,
                'from_number': call.from_number,
                'to_number': call.to_number,
                'duration': call.duration,
                'direction': call.direction,
                'disconnection_reason': call.disconnection_reason,
            })
        
        return Response({
            'lead_id': lead.id,
            'lead_name': f"{lead.name} {lead.surname or ''}".strip(),
            'call_count': len(call_data),
            'calls': call_data
        })
    
    @extend_schema(
        summary="Get lead statistics",
        description="Get statistics about leads",
        tags=["Lead Management"]
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get lead statistics"""
        total_leads = Lead.objects.count()
        leads_with_calls = Lead.objects.filter(mapping_lead_calllogs__isnull=False).distinct().count()
        leads_with_metadata = Lead.objects.exclude(meta_data={}).count()
        
        stats = {
            'total_leads': total_leads,
            'leads_with_calls': leads_with_calls,
            'leads_without_calls': total_leads - leads_with_calls,
            'leads_with_metadata': leads_with_metadata,
            'leads_without_metadata': total_leads - leads_with_metadata,
        }
        
        return Response(stats) 