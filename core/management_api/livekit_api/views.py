from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiResponse
from django.db import transaction
from django.utils import timezone

from core.models import LiveKitAgent
from .serializers import (
    LiveKitTokenRequestSerializer, 
    LiveKitTokenResponseSerializer,
    LiveKitAgentListSerializer
)
from .permissions import SuperuserOnlyPermission


@extend_schema_view(
    list=extend_schema(
        summary="📋 List LiveKit agents",
        description="""
        List all LiveKit agents (without exposing tokens).
        
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
                response=LiveKitAgentListSerializer(many=True),
                description="✅ LiveKit agents retrieved successfully"
            ),
            403: OpenApiResponse(description="🚫 Superuser access required")
        },
        tags=["LiveKit Token Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete LiveKit token",
        description="""
        Delete a LiveKit agent token permanently.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access
        - **✅ Superuser ONLY**: Can delete tokens
        
        **⚠️ Warning**:
        - This permanently deletes the agent token
        - Any systems using this token will lose authentication
        - Cannot be undone - token must be regenerated if needed
        
        **📝 Use Cases**:
        - Remove compromised tokens
        - Clean up unused agent tokens
        - Revoke access for decommissioned agents
        """,
        responses={
            204: OpenApiResponse(description="✅ Token deleted successfully"),
            403: OpenApiResponse(description="🚫 Superuser access required"),
            404: OpenApiResponse(description="🚫 Token not found")
        },
        tags=["LiveKit Token Management"]
    ),
    create=extend_schema(exclude=True),  # Hidden - use generate_token instead
    update=extend_schema(exclude=True),  # Hidden - tokens cannot be updated
    partial_update=extend_schema(exclude=True),  # Hidden - tokens cannot be updated
)
class LiveKitTokenViewSet(viewsets.ModelViewSet):
    """
    🔐 **LiveKit Token Management (Superuser Only)**
    
    Manages LiveKit authentication tokens with strict access control:
    - **🚫 Staff and Regular Users**: No access
    - **✅ Superuser Only**: Can generate and manage tokens
    """
    queryset = LiveKitAgent.objects.all().order_by('-created_at')
    serializer_class = LiveKitAgentListSerializer
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
        summary="🔑 Generate LiveKit token",
        description="""
        Generate a new LiveKit authentication token for an agent.
        
        **🔐 Access Control**:
        - **❌ Regular Users**: Cannot access
        - **❌ Staff Members**: Cannot access  
        - **✅ Superuser ONLY**: Can generate tokens
        
        **📝 Token Management**:
        - Each agent name can have only ONE active token
        - If agent already exists, old token is replaced
        - Token expires after 1 year
        - Secure random string generation
        
        **🔄 Replacement Logic**:
        - Existing agent → Replace token, extend expiration
        - New agent → Create new record with fresh token
        
        **🛡️ Security Features**:
        - 64-character URL-safe random tokens
        - Automatic expiration handling
        - Unique constraints on agent names and tokens
        """,
        request=LiveKitTokenRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=LiveKitTokenResponseSerializer,
                description="✅ Token generated successfully",
                examples=[
                    OpenApiExample(
                        'New Token Generated',
                        summary='Successful token generation',
                        value={
                            'id': '123e4567-e89b-12d3-a456-426614174000',
                            'name': 'sales-agent-1',
                            'token': 'abcdef123456789...',
                            'created_at': '2024-01-15T10:30:00Z',
                            'expires_at': '2025-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="❌ Validation error",
                examples=[
                    OpenApiExample(
                        'Invalid Agent Name',
                        value={'agent_name': ['Agent name cannot be empty']}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="🚫 Superuser access required",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            )
        },
        tags=["LiveKit Token Management"]
    )
    @action(detail=False, methods=['post'])
    def generate_token(self, request):
        """
        Generate or replace a LiveKit authentication token for an agent.
        
        Only superusers can access this endpoint.
        Each agent name can have only one active token.
        """
        serializer = LiveKitTokenRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        agent_name = serializer.validated_data['agent_name']
        
        with transaction.atomic():
            # Check if agent already exists
            try:
                agent = LiveKitAgent.objects.get(name=agent_name)
                # Replace existing token
                agent.token = LiveKitAgent.generate_token()
                agent.expires_at = timezone.now() + timezone.timedelta(days=365)
                agent.save(update_fields=['token', 'expires_at'])
                
            except LiveKitAgent.DoesNotExist:
                # Create new agent
                agent = LiveKitAgent.objects.create(name=agent_name)
        
        response_serializer = LiveKitTokenResponseSerializer(agent)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED) 