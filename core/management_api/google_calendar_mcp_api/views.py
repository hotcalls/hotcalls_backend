from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import GoogleCalendarMCPAgent
from core.management_api.calendar_api.serializers import (
    GoogleCalendarMCPTokenRequestSerializer,
    GoogleCalendarMCPTokenResponseSerializer,
    GoogleCalendarMCPAgentListSerializer
)
from core.management_api.calendar_api.permissions import SuperuserOnlyPermission


@extend_schema_view(
    list=extend_schema(
        summary="📋 List Google Calendar MCP agents",
        description="""
        List all Google Calendar MCP agents (without exposing tokens).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access
        - **✅ Superuser ONLY**: Can view agent list
        
        **📊 Information Shown**:
        - Agent ID and name
        - Creation and expiration dates
        - Token validity status
        - **NO token values exposed**
        """,
        responses={
            200: OpenApiResponse(
                response=GoogleCalendarMCPAgentListSerializer(many=True),
                description="✅ Google Calendar MCP agents retrieved successfully"
            ),
            403: OpenApiResponse(description="🚫 Superuser access required")
        },
        tags=["Google Calendar MCP"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete Google Calendar MCP token",
        description="""
        Delete a Google Calendar MCP agent token permanently.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access
        - **✅ Superuser ONLY**: Can delete tokens
        """,
        responses={
            204: OpenApiResponse(description="✅ Token deleted successfully"),
            403: OpenApiResponse(description="🚫 Superuser access required"),
            404: OpenApiResponse(description="🚫 Token not found")
        },
        tags=["Google Calendar MCP"]
    ),
    create=extend_schema(exclude=True),  # Hidden - use generate_token instead
    update=extend_schema(exclude=True),  # Hidden - tokens cannot be updated
    partial_update=extend_schema(exclude=True),  # Hidden - tokens cannot be updated
)
class GoogleCalendarMCPTokenViewSet(viewsets.ModelViewSet):
    """
    🔐 **Google Calendar MCP Token Management (Superuser Only)**
    
    Manages Google Calendar MCP authentication tokens with strict access control:
    - **🚫 Staff and Regular Users**: No access
    - **✅ Superuser Only**: Can generate and manage tokens
    """
    queryset = GoogleCalendarMCPAgent.objects.all().order_by('-created_at')
    serializer_class = GoogleCalendarMCPAgentListSerializer
    permission_classes = [SuperuserOnlyPermission]
    
    def create(self, request, *args, **kwargs):
        """Block direct creation - use generate_token action instead"""
        return Response(
            {'detail': 'Use /generate_token/ endpoint to create tokens'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def update(self, request, *args, **kwargs):
        """Block updates - tokens should be replaced via generate_token"""
        return Response(
            {'detail': 'Tokens cannot be updated. Use /generate_token/ to replace.'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Block partial updates"""
        return Response(
            {'detail': 'Tokens cannot be updated. Use /generate_token/ to replace.'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    @extend_schema(
        summary="🔑 Generate Google Calendar MCP token",
        description="""
        Generate a new Google Calendar MCP authentication token for an agent.
        
        **🔐 Access Control**:
        - **✅ Superuser ONLY**: Can generate tokens
        
        **📝 Token Management**:
        - Each agent name can have only ONE active token
        - If agent already exists, old token is replaced
        - Token expires after 1 year
        - Secure random string generation
        """,
        request=GoogleCalendarMCPTokenRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=GoogleCalendarMCPTokenResponseSerializer,
                description="✅ Token generated successfully"
            ),
            400: OpenApiResponse(description="❌ Validation error"),
            403: OpenApiResponse(description="🚫 Superuser access required")
        },
        tags=["Google Calendar MCP"]
    )
    @action(detail=False, methods=['post'])
    def generate_token(self, request):
        """
        Generate or replace a Google Calendar MCP authentication token for an agent.
        
        Only superusers can access this endpoint.
        Each agent name can have only one active token.
        """
        serializer = GoogleCalendarMCPTokenRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        agent_name = serializer.validated_data['agent_name']
        
        with transaction.atomic():
            # Check if agent already exists
            try:
                agent = GoogleCalendarMCPAgent.objects.get(name=agent_name)
                # Replace existing token
                agent.token = GoogleCalendarMCPAgent.generate_token()
                agent.expires_at = timezone.now() + timezone.timedelta(days=365)
                agent.save(update_fields=['token', 'expires_at'])
                
            except GoogleCalendarMCPAgent.DoesNotExist:
                # Create new agent
                agent = GoogleCalendarMCPAgent.objects.create(name=agent_name)
        
        response_serializer = GoogleCalendarMCPTokenResponseSerializer(agent)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="🔑 Get Current MCP Token (Public)",
        description="""
        **🤖 FOR MCP CLIENTS ONLY**
        
        Get the current valid MCP token for automatic authentication.
        This endpoint allows MCP clients to automatically retrieve their token
        without manual synchronization.
        
        **🔐 Authentication:** No authentication required (public endpoint)
        **📝 Usage:** MCP clients can call this to get their current token
        **⚡ Auto-Sync:** Eliminates manual token synchronization
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Current MCP token retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Current Token',
                        value={
                            "agent_name": "google-calender-mcp",
                            "token": "CN8F-U3ycBSaEQKtS2sDAhJNAhTHFcNP4Qi-ljp5wJC-qZKgr3NKVPc",
                            "expires_at": "2026-08-02T22:03:29.801523Z",
                            "valid": True,
                            "message": "Current MCP token retrieved successfully"
                        }
                    )
                ]
            ),
            404: OpenApiResponse(description="❌ MCP agent not found")
        },
        tags=["Google Calendar MCP"]
    )
    @action(detail=False, methods=['get'], url_path='current-token', permission_classes=[])
    def get_current_token(self, request):
        """
        Get the current valid MCP token by agent name.
        
        **🤖 MCP Authentication Flow:**
        1. MCP sends GET request with ?agent_name=google-calender-mcp
        2. Backend validates agent name exists
        3. Backend returns token for that specific agent
        4. MCP uses token for authenticated requests
        
        **🔐 Security:** Agent must know its own name to get token
        """
        agent_name = request.GET.get('agent_name')
        
        if not agent_name:
            return Response({
                'error': 'Missing agent_name parameter',
                'message': 'Please provide agent_name in query parameters',
                'example': '/api/google-calendar-mcp/tokens/current-token/?agent_name=google-calender-mcp'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the specific MCP agent by name
            agent = GoogleCalendarMCPAgent.objects.get(name=agent_name)
            
            if not agent.is_valid():
                return Response({
                    'error': 'Token expired',
                    'message': f'Token for agent {agent_name} has expired',
                    'agent_name': agent_name,
                    'expires_at': agent.expires_at
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            return Response({
                'agent_name': agent.name,
                'token': agent.token,
                'expires_at': agent.expires_at,
                'valid': agent.is_valid(),
                'message': f'Token retrieved successfully for agent {agent_name}'
            })
            
        except GoogleCalendarMCPAgent.DoesNotExist:
            return Response({
                'error': 'MCP agent not found',
                'message': f'No agent found with name: {agent_name}',
                'agent_name': agent_name
            }, status=status.HTTP_404_NOT_FOUND) 