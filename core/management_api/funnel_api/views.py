from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, OpenApiResponse
import logging
from django.utils import timezone

from core.models import LeadFunnel, Agent
from .serializers import (
    LeadFunnelSerializer,
    LeadFunnelCreateSerializer,
    LeadFunnelUpdateSerializer,
    AssignAgentSerializer,
    UnassignAgentSerializer
)
from .filters import LeadFunnelFilter

logger = logging.getLogger(__name__)


@extend_schema(tags=['Lead Funnels'])
class LeadFunnelViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Lead Funnels
    
    Lead Funnels act as the bridge between lead sources (like Meta Lead Forms)
    and Agents. Each funnel can be assigned to one agent, establishing the
    routing for incoming leads.
    """
    permission_classes = [IsAuthenticated]
    filterset_class = LeadFunnelFilter
    
    def get_queryset(self):
        """Get funnels for user's workspaces with optimized queries"""
        user = self.request.user
        
        # Get user's workspaces
        user_workspaces = user.mapping_user_workspaces.all()
        
        # Optimize queries with select_related and prefetch_related
        queryset = LeadFunnel.objects.filter(
            workspace__in=user_workspaces
        ).select_related(
            'workspace',
            'meta_lead_form',
            'meta_lead_form__meta_integration',
            'agent',
            'agent__voice'
        ).annotate(
            lead_count=Count('leads')
        ).order_by('-created_at')
        
        return queryset
    
    def get_serializer_class(self):
        """Get appropriate serializer based on action"""
        if self.action == 'create':
            return LeadFunnelCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LeadFunnelUpdateSerializer
        return LeadFunnelSerializer
    
    @extend_schema(
        summary="List Lead Funnels",
        description="Get all lead funnels for your workspaces",
        responses={
            200: OpenApiResponse(
                response=LeadFunnelSerializer(many=True),
                description="List of lead funnels"
            )
        }
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Create Lead Funnel",
        description="Create a new lead funnel",
        request=LeadFunnelCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=LeadFunnelSerializer,
                description="Created lead funnel"
            )
        }
    )
    def create(self, request, *args, **kwargs):
        """Create a new lead funnel with atomic transaction"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            funnel = serializer.save()
            
        # Return with full serializer
        output_serializer = LeadFunnelSerializer(funnel)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="Update Lead Funnel",
        description="Update a lead funnel's name or active status",
        request=LeadFunnelUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=LeadFunnelSerializer,
                description="Updated lead funnel"
            )
        }
    )
    def update(self, request, *args, **kwargs):
        """Update funnel with atomic transaction"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            # Lock the record for update
            LeadFunnel.objects.select_for_update().get(id=instance.id)
            funnel = serializer.save()
        
        # Return with full serializer
        output_serializer = LeadFunnelSerializer(funnel)
        return Response(output_serializer.data)
    
    @extend_schema(
        summary="Assign Agent to Funnel",
        description="Assign an agent to handle leads from this funnel",
        request=AssignAgentSerializer,
        responses={
            200: OpenApiResponse(
                response=LeadFunnelSerializer,
                description="Funnel with assigned agent"
            ),
            400: OpenApiResponse(description="Invalid agent or already assigned")
        }
    )
    @action(detail=True, methods=['post'])
    def assign_agent(self, request, pk=None):
        """Assign an agent to this funnel (race condition safe)"""
        funnel = self.get_object()
        
        # Check if funnel already has an agent
        if hasattr(funnel, 'agent') and funnel.agent:
            return Response(
                {'error': f'Funnel already has agent {funnel.agent.name} assigned'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = AssignAgentSerializer(
            data=request.data,
            context={'request': request, 'funnel': funnel}
        )
        serializer.is_valid(raise_exception=True)
        
        agent = serializer.validated_data['agent_id']
        
        try:
            with transaction.atomic():
                # Lock both records to prevent race conditions
                locked_funnel = LeadFunnel.objects.select_for_update().get(id=funnel.id)
                locked_agent = Agent.objects.select_for_update().get(agent_id=agent.agent_id)
                
                # Double-check agent isn't assigned elsewhere
                if locked_agent.lead_funnel and locked_agent.lead_funnel != locked_funnel:
                    raise ValueError(f"Agent {locked_agent.name} was assigned to another funnel")
                
                # Double-check funnel doesn't have an agent
                if hasattr(locked_funnel, 'agent') and locked_funnel.agent:
                    raise ValueError(f"Funnel was assigned to {locked_funnel.agent.name}")
                
                # Assign agent to funnel
                locked_agent.lead_funnel = locked_funnel
                locked_agent.save(update_fields=['lead_funnel', 'updated_at'])
                
                logger.info(f"Assigned agent {locked_agent.name} to funnel {locked_funnel.id}")
        
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to assign agent: {str(e)}")
            return Response(
                {'error': 'Failed to assign agent'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Refresh and return updated funnel
        funnel.refresh_from_db()
        output_serializer = LeadFunnelSerializer(funnel)
        return Response(output_serializer.data)
    
    @extend_schema(
        summary="Unassign Agent from Funnel",
        description="Remove the agent assignment from this funnel",
        request=UnassignAgentSerializer,
        responses={
            200: OpenApiResponse(
                response=LeadFunnelSerializer,
                description="Funnel with agent unassigned"
            ),
            400: OpenApiResponse(description="No agent assigned")
        }
    )
    @action(detail=True, methods=['post'])
    def unassign_agent(self, request, pk=None):
        """Unassign agent from this funnel (race condition safe)"""
        funnel = self.get_object()
        
        # Check if funnel has an agent
        if not hasattr(funnel, 'agent') or not funnel.agent:
            return Response(
                {'error': 'Funnel has no agent assigned'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = UnassignAgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            with transaction.atomic():
                # Lock the agent record
                agent = Agent.objects.select_for_update().get(
                    agent_id=funnel.agent.agent_id
                )
                
                # Verify agent is still assigned to this funnel
                if agent.lead_funnel != funnel:
                    raise ValueError("Agent assignment changed")
                
                # Unassign agent
                agent.lead_funnel = None
                agent.save(update_fields=['lead_funnel', 'updated_at'])
                
                logger.info(f"Unassigned agent {agent.name} from funnel {funnel.id}")
        
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to unassign agent: {str(e)}")
            return Response(
                {'error': 'Failed to unassign agent'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Refresh and return updated funnel
        funnel.refresh_from_db()
        output_serializer = LeadFunnelSerializer(funnel)
        return Response(output_serializer.data)
    
    @extend_schema(
        summary="Get Funnel Statistics",
        description="Get statistics for a specific funnel",
        responses={
            200: OpenApiResponse(
                description="Funnel statistics"
            )
        }
    )
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get statistics for this funnel"""
        funnel = self.get_object()
        
        # Calculate statistics
        stats = {
            'funnel_id': str(funnel.id),
            'funnel_name': funnel.name,
            'is_active': funnel.is_active,
            'has_agent': funnel.has_agent,
            'agent_name': funnel.agent.name if funnel.has_agent else None,
            'total_leads': funnel.leads.count(),
            'leads_today': funnel.leads.filter(
                created_at__date=timezone.now().date()
            ).count(),
            'leads_this_week': funnel.leads.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),
            'leads_with_calls': funnel.leads.filter(
                call_task__isnull=False
            ).count(),
            'meta_form_name': funnel.meta_lead_form.name if funnel.meta_lead_form else None,
        }
        
        return Response(stats) 