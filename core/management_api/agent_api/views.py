from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.models import Agent, PhoneNumber
from .serializers import (
    AgentSerializer, AgentCreateSerializer, AgentUpdateSerializer,
    PhoneNumberSerializer, PhoneNumberCreateSerializer,
    AgentPhoneAssignmentSerializer
)
from .filters import AgentFilter, PhoneNumberFilter
from .permissions import AgentPermission, PhoneNumberPermission, AgentPhoneManagementPermission


@extend_schema_view(
    list=extend_schema(
        summary="List agents",
        description="Retrieve a list of agents (users see only agents in their workspaces, staff see all)",
        tags=["Agent Management"]
    ),
    create=extend_schema(
        summary="Create a new agent",
        description="Create a new agent (staff only)",
        tags=["Agent Management"]
    ),
    retrieve=extend_schema(
        summary="Get agent details",
        description="Retrieve detailed information about a specific agent",
        tags=["Agent Management"]
    ),
    update=extend_schema(
        summary="Update agent",
        description="Update all fields of an agent (staff only)",
        tags=["Agent Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update agent",
        description="Update specific fields of an agent (staff only)",
        tags=["Agent Management"]
    ),
    destroy=extend_schema(
        summary="Delete agent",
        description="Delete an agent (superuser only)",
        tags=["Agent Management"]
    ),
)
class AgentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Agent model operations
    
    Provides CRUD operations for agents:
    - Users can view agents in their workspaces
    - Staff can view all agents and create/modify them
    - Superusers can delete agents
    """
    queryset = Agent.objects.all()
    permission_classes = [AgentPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AgentFilter
    search_fields = ['voice', 'language', 'character', 'greeting', 'workspace__workspace_name']
    ordering_fields = ['created_at', 'updated_at', 'retry_interval']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return AgentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AgentUpdateSerializer
        return AgentSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return Agent.objects.all()
        else:
            # Regular users can only see agents in their workspaces
            return Agent.objects.filter(workspace__mapping_user_workspaces=user)
    
    def perform_create(self, serializer):
        """Only staff can create agents"""
        if not self.request.user.is_staff:
            raise PermissionError("Only staff can create agents")
        serializer.save()
    
    @extend_schema(
        summary="Get agent phone numbers",
        description="Get all phone numbers assigned to a specific agent",
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['get'])
    def phone_numbers(self, request, pk=None):
        """Get all phone numbers for a specific agent"""
        agent = self.get_object()
        phone_numbers = agent.mapping_agent_phonenumbers.all()
        serializer = PhoneNumberSerializer(phone_numbers, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Assign phone numbers to agent",
        description="Assign one or more phone numbers to an agent (staff only)",
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[AgentPhoneManagementPermission])
    def assign_phone_numbers(self, request, pk=None):
        """Assign phone numbers to an agent"""
        agent = self.get_object()
        serializer = AgentPhoneAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            phone_number_ids = serializer.validated_data['phone_number_ids']
            phone_numbers = PhoneNumber.objects.filter(id__in=phone_number_ids)
            
            # Add phone numbers to agent
            agent.mapping_agent_phonenumbers.add(*phone_numbers)
            
            return Response({
                'message': f'Successfully assigned {len(phone_numbers)} phone numbers to agent',
                'assigned_numbers': [pn.phonenumber for pn in phone_numbers]
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Remove phone numbers from agent",
        description="Remove one or more phone numbers from an agent (staff only)",
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[AgentPhoneManagementPermission])
    def remove_phone_numbers(self, request, pk=None):
        """Remove phone numbers from an agent"""
        agent = self.get_object()
        serializer = AgentPhoneAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            phone_number_ids = serializer.validated_data['phone_number_ids']
            phone_numbers = PhoneNumber.objects.filter(id__in=phone_number_ids)
            
            # Remove phone numbers from agent
            agent.mapping_agent_phonenumbers.remove(*phone_numbers)
            
            return Response({
                'message': f'Successfully removed {len(phone_numbers)} phone numbers from agent',
                'removed_numbers': [pn.phonenumber for pn in phone_numbers]
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Get agent configuration",
        description="Get the full configuration of an agent including calendar settings",
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['get'])
    def config(self, request, pk=None):
        """Get agent configuration"""
        agent = self.get_object()
        
        config = {
            'basic_info': {
                'voice': agent.voice,
                'language': agent.language,
                'greeting': agent.greeting,
                'character': agent.character,
            },
            'scheduling': {
                'retry_interval': agent.retry_interval,
                'workdays': agent.workdays,
                'call_from': agent.call_from,
                'call_to': agent.call_to,
            },
            'phone_numbers': [pn.phonenumber for pn in agent.mapping_agent_phonenumbers.all()],
            'calendar_config': agent.calendar_configuration.id if agent.calendar_configuration else None,
            'config_id': agent.config_id,
        }
        
        return Response(config)


@extend_schema_view(
    list=extend_schema(
        summary="List phone numbers",
        description="Retrieve a list of all phone numbers with filtering capabilities",
        tags=["Agent Management"]
    ),
    create=extend_schema(
        summary="Create a new phone number",
        description="Create a new phone number (staff only)",
        tags=["Agent Management"]
    ),
    retrieve=extend_schema(
        summary="Get phone number details",
        description="Retrieve detailed information about a specific phone number",
        tags=["Agent Management"]
    ),
    update=extend_schema(
        summary="Update phone number",
        description="Update a phone number (staff only)",
        tags=["Agent Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update phone number",
        description="Update specific fields of a phone number (staff only)",
        tags=["Agent Management"]
    ),
    destroy=extend_schema(
        summary="Delete phone number",
        description="Delete a phone number (superuser only)",
        tags=["Agent Management"]
    ),
)
class PhoneNumberViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PhoneNumber model operations
    
    Provides CRUD operations for phone numbers:
    - All users can view phone numbers
    - Staff can create/modify phone numbers
    - Superusers can delete phone numbers
    """
    queryset = PhoneNumber.objects.all()
    permission_classes = [PhoneNumberPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PhoneNumberFilter
    search_fields = ['phonenumber']
    ordering_fields = ['phonenumber', 'created_at', 'is_active']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PhoneNumberCreateSerializer
        return PhoneNumberSerializer
    
    @extend_schema(
        summary="Get phone number agents",
        description="Get all agents that use this phone number",
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['get'])
    def agents(self, request, pk=None):
        """Get all agents that use this phone number"""
        phone_number = self.get_object()
        agents = phone_number.mapping_agent_phonenumbers.all()
        serializer = AgentSerializer(agents, many=True)
        return Response(serializer.data) 