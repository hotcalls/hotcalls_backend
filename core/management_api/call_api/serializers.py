from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import CallLog, Lead


class CallLogSerializer(serializers.ModelSerializer):
    """Serializer for CallLog model"""
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    lead_surname = serializers.CharField(source='lead.surname', read_only=True)
    lead_email = serializers.CharField(source='lead.email', read_only=True)
    duration_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = CallLog
        fields = [
            'id', 'lead', 'lead_name', 'lead_surname', 'lead_email',
            'timestamp', 'from_number', 'to_number', 'duration', 
            'duration_formatted', 'disconnection_reason', 'direction', 'updated_at'
        ]
        read_only_fields = ['id', 'timestamp', 'updated_at']
    
    def validate_duration(self, value):
        """Validate duration is not negative"""
        if value < 0:
            raise serializers.ValidationError("Duration cannot be negative")
        return value
    
    @extend_schema_field(serializers.CharField)
    def get_duration_formatted(self, obj) -> str:
        """Format duration in minutes and seconds"""
        minutes = obj.duration // 60
        seconds = obj.duration % 60
        return f"{minutes}m {seconds}s"


class CallLogCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating call logs"""
    
    class Meta:
        model = CallLog
        fields = [
            'lead', 'from_number', 'to_number', 'duration',
            'disconnection_reason', 'direction'
        ]
    
    def validate_duration(self, value):
        """Validate duration is not negative"""
        if value < 0:
            raise serializers.ValidationError("Duration cannot be negative")
        return value


class CallLogAnalyticsSerializer(serializers.Serializer):
    """Serializer for call analytics"""
    total_calls = serializers.IntegerField(read_only=True)
    calls_today = serializers.IntegerField(read_only=True)
    calls_this_week = serializers.IntegerField(read_only=True)
    calls_this_month = serializers.IntegerField(read_only=True)
    avg_duration = serializers.FloatField(read_only=True)
    total_duration = serializers.IntegerField(read_only=True)
    inbound_calls = serializers.IntegerField(read_only=True)
    outbound_calls = serializers.IntegerField(read_only=True) 