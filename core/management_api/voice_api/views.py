from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import Voice
from .serializers import VoiceSerializer, VoiceCreateSerializer, VoiceUpdateSerializer
from .filters import VoiceFilter
from .permissions import VoicePermission


@extend_schema_view(
    list=extend_schema(
        summary="🔊 List voices",
        description="""
        Retrieve all voice configurations in the system with filtering and search capabilities.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: No access to voice management
        - **✅ Staff Members**: Can view all voice configurations  
        - **✅ Superusers**: Can view all voice configurations
        
        **🎯 Voice Management**:
        - Centralized voice configuration database
        - Support for multiple voice providers
        - Agent assignment tracking
        
        **🔍 Search & Filtering**:
        - Search by voice external ID or provider
        - Filter by provider (OpenAI, ElevenLabs, Google, etc.)
        - Filter by agent assignment status
        """,
        responses={
            200: OpenApiResponse(
                response=VoiceSerializer(many=True),
                description="✅ Successfully retrieved voice configurations",
                examples=[
                    OpenApiExample(
                        'Voice List',
                        summary='Available voice configurations',
                        value={
                            'count': 25,
                            'results': [
                                {
                                    'id': 'voice-uuid-1',
                                    'voice_external_id': 'alloy',
                                    'provider': 'openai',
                                    'agent_count': 3,
                                    'created_at': '2024-01-10T09:00:00Z'
                                },
                                {
                                    'id': 'voice-uuid-2', 
                                    'voice_external_id': '21m00Tcm4TlvDq8ikWAM',
                                    'provider': 'elevenlabs',
                                    'agent_count': 1,
                                    'created_at': '2024-01-12T14:30:00Z'
                                }
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required for voice management")
        },
        tags=["Voice Management"]
    ),
    create=extend_schema(
        summary="➕ Create new voice",
        description="""
        Add a new voice configuration to the system (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot create voice configurations
        - **✅ Staff Members**: Can create new voice configurations
        - **✅ Superusers**: Can create new voice configurations
        
        **📝 Required Fields**:
        - `voice_external_id`: External voice ID from provider (required)
        - `provider`: Voice provider - openai, elevenlabs, google, azure, aws (required)
        
        **🔒 Validation Rules**:
        - Voice external ID cannot be empty or exceed 255 characters
        - Provider must be from allowed list
        - Combination of external ID + provider must be unique
        """,
        request=VoiceCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=VoiceSerializer,
                description="✅ Voice configuration created successfully",
                examples=[
                    OpenApiExample(
                        'New Voice Created',
                        summary='Successfully created voice configuration',
                        value={
                            'id': 'new-voice-uuid',
                            'voice_external_id': 'nova',
                            'provider': 'openai',
                            'agent_count': 0,
                            'created_at': '2024-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Check voice external ID and provider"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required")
        },
        tags=["Voice Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get voice details", 
        description="""
        Retrieve detailed information about a specific voice configuration.
        
        **🔐 Permission Requirements**: Staff access required
        
        **📊 Detailed Information**:
        - Voice external ID and provider details
        - Number of agents using this voice
        - Creation and modification timestamps
        """,
        responses={
            200: OpenApiResponse(response=VoiceSerializer, description="✅ Voice details retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required"),
            404: OpenApiResponse(description="🚫 Voice not found")
        },
        tags=["Voice Management"]
    ),
    update=extend_schema(
        summary="✏️ Update voice configuration",
        description="""
        Update voice configuration details (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        
        **📝 Updatable Fields**:
        - `voice_external_id`: External voice ID from provider
        - `provider`: Voice provider
        
        **⚠️ Update Considerations**:
        - Updating voice affects all agents using this voice
        - Ensure new configuration is compatible with existing agents
        - Combination of external ID + provider must remain unique
        """,
        request=VoiceUpdateSerializer,
        responses={
            200: OpenApiResponse(response=VoiceSerializer, description="✅ Voice updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required"),
            404: OpenApiResponse(description="🚫 Voice not found")
        },
        tags=["Voice Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update voice",
        description="""
        Update specific fields of a voice configuration (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=VoiceUpdateSerializer,
        responses={
            200: OpenApiResponse(response=VoiceSerializer, description="✅ Voice updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required"),
            404: OpenApiResponse(description="🚫 Voice not found")
        },
        tags=["Voice Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete voice configuration",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Delete a voice configuration.**
        
        **🔐 Permission Requirements**: Staff access required
        
        **💥 Consequences**:
        - Voice configuration permanently removed
        - All agents using this voice will have voice set to NULL
        - Cannot be undone - ensure no agents depend on this voice
        
        **🛡️ Safety Recommendations**:
        - Check agent_count before deletion
        - Reassign agents to different voices first
        - Consider impact on active call operations
        """,
        responses={
            204: OpenApiResponse(description="✅ Voice deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required"),
            404: OpenApiResponse(description="🚫 Voice not found")
        },
        tags=["Voice Management"]
    ),
)
class VoiceViewSet(viewsets.ModelViewSet):
    """
    🔊 **Voice Configuration Management with Staff-Only Access**
    
    Manages voice configurations for AI agents:
    - **🔒 Staff Only**: All voice operations require staff privileges
    - **🎯 Voice Providers**: Support for OpenAI, ElevenLabs, Google, Azure, AWS
    - **📊 Agent Tracking**: Monitor which agents use each voice
    """
    queryset = Voice.objects.all()
    permission_classes = [VoicePermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = VoiceFilter
    search_fields = ['voice_external_id', 'provider']
    ordering_fields = ['voice_external_id', 'provider', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return VoiceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return VoiceUpdateSerializer
        return VoiceSerializer
    
    @extend_schema(
        summary="📊 Voice usage statistics",
        description="""
        Get comprehensive statistics about voice usage across the system.
        
        **📈 Statistics Include**:
        - Total number of voices by provider
        - Agent assignment distribution  
        - Most/least used voices
        - Provider popularity rankings
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Voice statistics retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Voice Statistics',
                        summary='System-wide voice usage stats',
                        value={
                            'total_voices': 15,
                            'total_assigned_agents': 42,
                            'provider_breakdown': {
                                'openai': {'voices': 8, 'agents': 25},
                                'elevenlabs': {'voices': 5, 'agents': 15},
                                'google': {'voices': 2, 'agents': 2}
                            },
                            'most_used_voice': {
                                'id': 'voice-uuid',
                                'voice_external_id': 'alloy',
                                'provider': 'openai',
                                'agent_count': 12
                            },
                            'unassigned_voices': 3
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required")
        },
        tags=["Voice Management"],
        methods=["GET"]
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get voice usage statistics"""
        from django.db.models import Count
        
        # Get total counts
        total_voices = Voice.objects.count()
        
        # Get voices with agent counts
        voices_with_counts = Voice.objects.annotate(
            agent_count=Count('mapping_voice_agents')
        )
        
        total_assigned_agents = sum(v.agent_count for v in voices_with_counts)
        
        # Provider breakdown
        provider_stats = {}
        for voice in voices_with_counts:
            if voice.provider not in provider_stats:
                provider_stats[voice.provider] = {'voices': 0, 'agents': 0}
            provider_stats[voice.provider]['voices'] += 1
            provider_stats[voice.provider]['agents'] += voice.agent_count
        
        # Most used voice
        most_used = voices_with_counts.order_by('-agent_count').first()
        most_used_data = None
        if most_used:
            most_used_data = {
                'id': str(most_used.id),
                'voice_external_id': most_used.voice_external_id,
                'provider': most_used.provider,
                'agent_count': most_used.agent_count
            }
        
        # Unassigned voices
        unassigned_voices = voices_with_counts.filter(agent_count=0).count()
        
        return Response({
            'total_voices': total_voices,
            'total_assigned_agents': total_assigned_agents,
            'provider_breakdown': provider_stats,
            'most_used_voice': most_used_data,
            'unassigned_voices': unassigned_voices
        }) 