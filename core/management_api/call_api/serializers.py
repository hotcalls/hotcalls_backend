from rest_framework import serializers
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
    
    def get_duration_formatted(self, obj):
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


class CallLogAnalyticsSerializer(serializers.Serializer):
    """Serializer for call analytics"""
    total_calls = serializers.IntegerField()
    total_duration = serializers.IntegerField()
    average_duration = serializers.FloatField()
    inbound_calls = serializers.IntegerField()
    outbound_calls = serializers.IntegerField()
    successful_calls = serializers.IntegerField()
    failed_calls = serializers.IntegerField() 