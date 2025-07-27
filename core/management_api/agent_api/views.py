from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import Agent, PhoneNumber
from .serializers import (
    AgentSerializer, AgentCreateSerializer, AgentUpdateSerializer, PhoneNumberSerializer,
    AgentPhoneAssignmentSerializer, AgentConfigSerializer
)
from .filters import AgentFilter, PhoneNumberFilter
from .permissions import AgentPermission, PhoneNumberPermission, AgentPhoneManagementPermission


@extend_schema_view(
    list=extend_schema(
        summary="🤖 List AI agents",
        description="""
        Retrieve AI agents based on your workspace access and role.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see agents in their workspaces (filtered)
        - **Staff Members**: Can view all agents in the system
        - **Superusers**: Full access to all agent data
        
        **📊 Response Filtering**:
        - Regular users see only workspace-scoped agents
        - Staff/Superusers see all agents with full configuration
        
        **🎯 Use Cases**:
        - Agent management interface
        - Resource allocation overview
        - Workspace agent inventory
        """,
        responses={
            200: OpenApiResponse(
                response=AgentSerializer(many=True),
                description="✅ Successfully retrieved agents based on access level",
                examples=[
                    OpenApiExample(
                        'Regular User Response',
                        summary='User sees only workspace agents',
                        description='Regular users are filtered to see only agents in their workspaces',
                        value={
                            'count': 3,
                            'results': [
                                {
                                    'agent_id': 'agent-uuid-1',
                                    'workspace_name': 'My Team',
                                    'greeting': 'Hello! How can I help you today?',
                                    'voice': 'en-US-AriaNeural',
                                    'language': 'English',
                                    'phone_number_count': 2
                                }
                            ]
                        }
                    ),
                    OpenApiExample(
                        'Staff User Response',
                        summary='Staff sees all agents',
                        description='Staff members can view all agents in the system',
                        value={
                            'count': 15,
                            'results': [
                                {'agent_id': 'uuid1', 'workspace_name': 'Sales', 'voice': 'en-US-Jenny'},
                                {'agent_id': 'uuid2', 'workspace_name': 'Support', 'voice': 'en-US-Guy'}
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access agents")
        },
        tags=["Agent Management"]
    ),
    create=extend_schema(
        summary="➕ Create new AI agent",
        description="""
        Create a new AI agent for a workspace.
        
        **🔐 Permission Requirements**:
        - **✅ Regular Users**: Can create agents in workspaces they belong to
        - **✅ Staff Members**: Can create agents for any workspace
        - **✅ Superusers**: Can create agents for any workspace
        
        **🤖 AI Agent Configuration**:
        - Voice and language settings
        - Greeting and personality setup
        - Working hours and availability
        - Calendar integration options
        
        **📝 Required Information**:
        - `workspace`: Target workspace ID (must be a workspace you belong to)
        - `name`: Agent name
        - `greeting_inbound`: Greeting for inbound calls
        - `greeting_outbound`: Greeting for outbound calls
        - `voice`: Voice configuration
        - `language`: Agent language
        - `workdays`: Available working days
        - `call_from`/`call_to`: Working hours
        - `character`: Agent personality description
        """,
        request=AgentCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=AgentSerializer,
                description="✅ AI agent created successfully",
                examples=[
                    OpenApiExample(
                        'New Agent Created',
                        summary='Successfully created AI agent',
                        value={
                            'agent_id': 'new-agent-uuid',
                            'workspace_name': 'Customer Support',
                            'name': 'Sales Assistant',
                            'greeting_inbound': 'Hi! I\'m your AI assistant. How can I help you today?',
                            'greeting_outbound': 'Hello! I\'m calling from [Company]. Is this a good time to talk?',
                            'voice': 'en-US-AriaNeural',
                            'language': 'English',
                            'phone_number_count': 0,
                            'created_at': '2024-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Check agent configuration or workspace access"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - You can only create agents in workspaces you belong to",
                examples=[
                    OpenApiExample(
                        'Workspace Access Denied',
                        summary='User attempted to create agent in workspace they don\'t belong to',
                        value={'workspace': ['You can only create agents in workspaces you belong to']}
                    )
                ]
            )
        },
        tags=["Agent Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get AI agent details",
        description="""
        Retrieve detailed information about a specific AI agent.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only access agents in their workspaces
        - **Staff Members**: Can access any agent details
        - **Superusers**: Full access to any agent configuration
        
        **🛡️ Access Control**:
        - Users get 404 for agents outside their workspaces (security)
        - Staff can see all configuration details
        - Includes phone number assignments and calendar config
        """,
        responses={
            200: OpenApiResponse(response=AgentSerializer, description="✅ Agent details retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Agent not in your workspace"),
            404: OpenApiResponse(description="🚫 Agent not found or access denied")
        },
        tags=["Agent Management"]
    ),
    update=extend_schema(
        summary="✏️ Update AI agent",
        description="""
        Update AI agent configuration (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify agents
        - **✅ Staff Members**: Can update any agent configuration
        - **✅ Superusers**: Can update any agent configuration
        
        **⚠️ Configuration Impact**:
        - May affect ongoing calls and interactions
        - Changes voice, personality, and behavior
        - Updates working hours and availability
        """,
        request=AgentCreateSerializer,
        responses={
            200: OpenApiResponse(response=AgentSerializer, description="✅ Agent updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update AI agent",
        description="""
        Update specific fields of an AI agent (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=AgentCreateSerializer,
        responses={
            200: OpenApiResponse(response=AgentSerializer, description="✅ Agent updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete AI agent",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete an AI agent.**
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: No access to agent deletion
        - **❌ Staff Members**: Cannot delete agents
        - **✅ Superuser ONLY**: Can delete agents
        
        **💥 Critical Impact**:
        - Removes agent and all configurations
        - Affects phone number assignments
        - Disrupts ongoing call operations
        - Cannot be undone
        
        **🛡️ Safety Considerations**:
        - Ensure no active calls using this agent
        - Reassign phone numbers before deletion
        - Consider agent deactivation instead
        """,
        responses={
            204: OpenApiResponse(description="✅ Agent deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Only superusers can delete agents",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        summary='Non-superuser attempted agent deletion',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    ),
)
class AgentViewSet(viewsets.ModelViewSet):
    """
    🤖 **AI Agent Management with Workspace-Based Access Control**
    
    Manages AI agents with workspace-filtered access:
    - **👤 Regular Users**: Can view and create agents in their workspaces
    - **👔 Staff**: Full agent administration across all workspaces
    - **🔧 Superusers**: Complete agent control including deletion
    """
    queryset = Agent.objects.all()
    permission_classes = [AgentPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AgentFilter
    search_fields = [
        'name', 'status', 'greeting_inbound', 'greeting_outbound', 
        'language', 'character', 'workspace__workspace_name',
        'voice__provider', 'voice__voice_external_id'
    ]
    ordering_fields = [
        'created_at', 'updated_at', 'name', 'status', 'language',
        'voice__provider', 'voice__voice_external_id'
    ]
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
            return Agent.objects.filter(workspace__users=user)
    
    @extend_schema(
        summary="📞 Get agent phone numbers",
        description="""
        Retrieve all phone numbers assigned to a specific agent.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can view phone numbers for agents in their workspaces
        - **Staff Members**: Can view phone numbers for any agent
        - **Superusers**: Full access to agent phone assignments
        
        **📊 Phone Number Information**:
        - Assigned phone numbers and status
        - Phone number availability and configuration
        - Assignment dates and history
        """,
        responses={
            200: OpenApiResponse(
                response=PhoneNumberSerializer(many=True),
                description="✅ Agent phone numbers retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Agent not in your workspace"),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['get'])
    def phone_numbers(self, request, pk=None):
        """Get all phone numbers assigned to an agent"""
        agent = self.get_object()
        phone_numbers = agent.phone_numbers.all()
        serializer = PhoneNumberSerializer(phone_numbers, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="➕ Assign phone numbers to agent",
        description="""
        Assign one or multiple phone numbers to an agent (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot manage phone assignments
        - **✅ Staff Members**: Can assign phone numbers to any agent
        - **✅ Superusers**: Can assign phone numbers to any agent
        
        **📝 Required Information**:
        - `phone_number_ids`: Array of phone number IDs to assign
        
        **🔄 Resource Allocation**:
        - Phone numbers can be shared across multiple agents
        - Establishes agent-phone relationships
        - Enables agent to make/receive calls on assigned numbers
        """,
        request=AgentPhoneAssignmentSerializer,
        responses={
            200: OpenApiResponse(
                description="✅ Phone numbers assigned to agent successfully",
                examples=[
                    OpenApiExample(
                        'Phone Numbers Assigned',
                        summary='Multiple phone numbers assigned',
                        value={
                            'message': 'Phone numbers assigned successfully',
                            'assigned_numbers': ['+1234567890', '+1987654321'],
                            'total_assigned': 2
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Invalid phone number IDs"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[AgentPhoneManagementPermission])
    def assign_phone_numbers(self, request, pk=None):
        """Assign phone numbers to an agent (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can manage agent phone numbers'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        agent = self.get_object()
        serializer = AgentPhoneAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            phone_number_ids = serializer.validated_data['phone_number_ids']
            phone_numbers = PhoneNumber.objects.filter(id__in=phone_number_ids)
            
            # Track already assigned numbers
            current_phone_ids = set(agent.phone_numbers.values_list('id', flat=True))
            requested_phone_ids = set(phone_numbers.values_list('id', flat=True))
            
            already_assigned_ids = current_phone_ids.intersection(requested_phone_ids)
            new_assignment_ids = requested_phone_ids - current_phone_ids
            
            # Only add new assignments
            new_phones = phone_numbers.filter(id__in=new_assignment_ids)
            agent.phone_numbers.add(*new_phones)
            
            response_data = {
                'message': 'Phone numbers assigned successfully',
                'assigned_numbers': [pn.phonenumber for pn in new_phones],
                'total_assigned': len(new_phones)
            }
            
            # Include already assigned numbers if any
            if already_assigned_ids:
                already_assigned_phones = phone_numbers.filter(id__in=already_assigned_ids)
                response_data['already_assigned'] = [pn.phonenumber for pn in already_assigned_phones]
            
            return Response(response_data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="➖ Remove phone numbers from agent",
        description="""
        Remove one or multiple phone numbers from an agent (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        
        **⚠️ Impact**:
        - Removes agent's ability to use those numbers
        - May affect ongoing call operations
        - Numbers become available for other agents
        """,
        request=AgentPhoneAssignmentSerializer,
        responses={
            200: OpenApiResponse(description="✅ Phone numbers removed from agent successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['delete'], permission_classes=[AgentPhoneManagementPermission])
    def remove_phone_numbers(self, request, pk=None):
        """Remove phone numbers from an agent (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can manage agent phone numbers'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        agent = self.get_object()
        serializer = AgentPhoneAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            phone_number_ids = serializer.validated_data['phone_number_ids']
            phone_numbers = PhoneNumber.objects.filter(id__in=phone_number_ids)
            
            # Track which numbers are actually assigned
            current_phone_ids = set(agent.phone_numbers.values_list('id', flat=True))
            requested_phone_ids = set(phone_numbers.values_list('id', flat=True))
            
            assigned_ids = current_phone_ids.intersection(requested_phone_ids)
            not_assigned_ids = requested_phone_ids - current_phone_ids
            
            # Only remove numbers that are actually assigned
            phones_to_remove = phone_numbers.filter(id__in=assigned_ids)
            agent.phone_numbers.remove(*phones_to_remove)
            
            response_data = {
                'message': 'Phone numbers removed successfully',
                'removed_numbers': [pn.phonenumber for pn in phones_to_remove],
                'total_removed': len(phones_to_remove)
            }
            
            # Include not assigned numbers if any
            if not_assigned_ids:
                not_assigned_phones = phone_numbers.filter(id__in=not_assigned_ids)
                response_data['not_assigned'] = [pn.phonenumber for pn in not_assigned_phones]
            
            return Response(response_data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="⚙️ Get agent configuration",
        description="""
        Retrieve complete configuration details for an agent.
        
        **🔐 Permission Requirements**: Same as agent detail access
        
        **📊 Configuration Details**:
        - Voice and language settings
        - Working hours and availability
        - Calendar integration configuration
        - Phone number assignments
        - Character and greeting setup
        """,
        responses={
            200: OpenApiResponse(
                response=AgentConfigSerializer,
                description="✅ Agent configuration retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Agent not found")
        },
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['get'])
    def config(self, request, pk=None):
        """Get agent configuration details"""
        agent = self.get_object()
        serializer = AgentConfigSerializer(agent)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="📞 List phone numbers",
        description="""
        Retrieve all available phone numbers in the system.
        
        **🔐 Permission Requirements**:
        - **✅ All Authenticated Users**: Can view all phone numbers
        - **✅ Staff/Superuser**: Same access level as regular users
        
        **📊 System Resources**:
        - All phone numbers available for agent assignment
        - Phone number status and availability
        - Current agent assignments
        
        **🎯 Use Cases**:
        - Phone number inventory
        - Agent assignment planning
        - Resource availability checking
        """,
        responses={
            200: OpenApiResponse(
                response=PhoneNumberSerializer(many=True),
                description="✅ Successfully retrieved all phone numbers",
                examples=[
                    OpenApiExample(
                        'Phone Numbers List',
                        summary='Available phone numbers',
                        value={
                            'count': 10,
                            'results': [
                                {
                                    'id': 'phone-uuid-1',
                                    'phonenumber': '+1234567890',
                                    'is_active': True,
                                    'agent_count': 2,
                                    'created_at': '2024-01-10T09:00:00Z'
                                },
                                {
                                    'id': 'phone-uuid-2',
                                    'phonenumber': '+1987654321',
                                    'is_active': True,
                                    'agent_count': 0,
                                    'created_at': '2024-01-12T14:30:00Z'
                                }
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to view phone numbers")
        },
        tags=["Agent Management"]
    ),
    create=extend_schema(
        summary="➕ Create new phone number",
        description="""
        Add a new phone number to the system for agent assignment.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot create phone numbers
        - **✅ Staff Members**: Can add new phone numbers
        - **✅ Superusers**: Can add new phone numbers
        
        **📞 Phone Number Management**:
        - Adds phone numbers to system inventory
        - Makes numbers available for agent assignment
        - Sets up system resources for call handling
        
        **📝 Required Information**:
        - `phonenumber`: Phone number in international format
        - `is_active`: Whether the number is available for use
        """,
        request=PhoneNumberSerializer,
        responses={
            201: OpenApiResponse(
                response=PhoneNumberSerializer,
                description="✅ Phone number created successfully"
            ),
            400: OpenApiResponse(description="❌ Validation error - Phone number format or uniqueness"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required")
        },
        tags=["Agent Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get phone number details",
        description="""Get detailed information about a specific phone number.""",
        responses={
            200: OpenApiResponse(response=PhoneNumberSerializer, description="✅ Phone number details retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Phone number not found")
        },
        tags=["Agent Management"]
    ),
    update=extend_schema(
        summary="✏️ Update phone number",
        description="""Update phone number information (Staff only).""",
        request=PhoneNumberSerializer,
        responses={
            200: OpenApiResponse(response=PhoneNumberSerializer, description="✅ Phone number updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Phone number not found")
        },
        tags=["Agent Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update phone number",
        description="""Update specific fields of a phone number (Staff only).""",
        request=PhoneNumberSerializer,
        responses={
            200: OpenApiResponse(response=PhoneNumberSerializer, description="✅ Phone number updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Phone number not found")
        },
        tags=["Agent Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete phone number",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete a phone number.**
        
        **🔐 Permission Requirements**: Superuser only
        
        **💥 Impact**: Removes phone number and all agent assignments
        """,
        responses={
            204: OpenApiResponse(description="✅ Phone number deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Superuser access required"),
            404: OpenApiResponse(description="🚫 Phone number not found")
        },
        tags=["Agent Management"]
    ),
)
class PhoneNumberViewSet(viewsets.ModelViewSet):
    """
    📞 **Phone Number Management - System Resource Administration**
    
    Manages phone numbers with role-based access:
    - **👤 All Users**: Can view available phone numbers
    - **👔 Staff**: Can create and modify phone numbers
    - **🔧 Superusers**: Can delete phone numbers
    """
    queryset = PhoneNumber.objects.all()
    serializer_class = PhoneNumberSerializer
    permission_classes = [PhoneNumberPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PhoneNumberFilter
    search_fields = ['phonenumber']
    ordering_fields = ['phonenumber', 'created_at', 'is_active']
    ordering = ['phonenumber']
    
    @extend_schema(
        summary="🤖 Get phone number agents",
        description="""
        Retrieve all agents that are assigned to this phone number.
        
        **🔐 Permission Requirements**: All authenticated users
        
        **📊 Assignment Information**:
        - All agents using this phone number
        - Agent configuration and workspace details
        - Assignment relationships and status
        """,
        responses={
            200: OpenApiResponse(
                response=AgentSerializer(many=True),
                description="✅ Phone number agents retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            404: OpenApiResponse(description="🚫 Phone number not found")
        },
        tags=["Agent Management"]
    )
    @action(detail=True, methods=['get'])
    def agents(self, request, pk=None):
        """Get all agents assigned to this phone number"""
        phone_number = self.get_object()
        agents = phone_number.mapping_agent_phonenumbers.all()
        # Filter agents based on user permissions
        user = request.user
        if not user.is_staff:
            agents = agents.filter(workspace__users=user)
        
        serializer = AgentSerializer(agents, many=True)
        return Response(serializer.data) 