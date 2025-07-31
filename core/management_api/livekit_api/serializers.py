from rest_framework import serializers
from core.models import LiveKitAgent


class LiveKitTokenRequestSerializer(serializers.Serializer):
    """
    Serializer for LiveKit token generation request
    """
    agent_name = serializers.CharField(
        max_length=255,
        help_text="Unique agent name for LiveKit authentication"
    )
    
    def validate_agent_name(self, value):
        """Ensure agent name is valid"""
        if not value.strip():
            raise serializers.ValidationError("Agent name cannot be empty")
        return value.strip()


class LiveKitTokenResponseSerializer(serializers.ModelSerializer):
    """
    Serializer for LiveKit token response
    """
    class Meta:
        model = LiveKitAgent
        fields = ['id', 'name', 'token', 'created_at', 'expires_at']
        read_only_fields = ['id', 'token', 'created_at', 'expires_at']


class LiveKitAgentListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing LiveKit agents (no token exposure)
    """
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = LiveKitAgent
        fields = ['id', 'name', 'created_at', 'expires_at', 'is_valid']
        read_only_fields = ['id', 'name', 'created_at', 'expires_at', 'is_valid']
    
    def get_is_valid(self, obj):
        """Return if token is still valid"""
        return obj.is_valid() 