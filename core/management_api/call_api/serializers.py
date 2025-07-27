from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import CallLog, Lead, Agent


class CallLogSerializer(serializers.ModelSerializer):
    """Serializer for CallLog model"""
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    lead_surname = serializers.CharField(source='lead.surname', read_only=True)
    lead_email = serializers.CharField(source='lead.email', read_only=True)
    agent_workspace_name = serializers.CharField(source='agent.workspace.workspace_name', read_only=True)
    duration_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = CallLog
        fields = [
            'id', 'lead', 'lead_name', 'lead_surname', 'lead_email', 
            'agent', 'agent_workspace_name',
            'timestamp', 'from_number', 'to_number', 'duration', 
            'duration_formatted', 'disconnection_reason', 'direction', 
            'status', 'appointment_datetime', 'updated_at'
        ]
        read_only_fields = ['id', 'timestamp', 'updated_at']
    
    def validate_duration(self, value):
        """Validate duration is not negative"""
        if value < 0:
            raise serializers.ValidationError("Duration cannot be negative")
        return value
    
    def validate(self, attrs):
        """Cross-field validation for appointment logic and agent workspace"""
        status = attrs.get('status')
        appointment_datetime = attrs.get('appointment_datetime')
        agent = attrs.get('agent')
        lead = attrs.get('lead')
        
        # If updating, get existing values for fields not being updated
        if self.instance:
            status = status or self.instance.status
            appointment_datetime = appointment_datetime if 'appointment_datetime' in attrs else self.instance.appointment_datetime
            agent = agent or self.instance.agent
            lead = lead or self.instance.lead
        
        # Appointment datetime validation
        if status == 'appointment_scheduled':
            if not appointment_datetime:
                raise serializers.ValidationError({
                    'appointment_datetime': 'Appointment datetime is required when status is "appointment_scheduled"'
                })
        elif appointment_datetime:
            raise serializers.ValidationError({
                'appointment_datetime': 'Appointment datetime should only be set when status is "appointment_scheduled"'
            })
        
        # Agent workspace validation
        if agent and lead:
            # Check if agent belongs to a workspace that the lead could be associated with
            # For now, we'll just validate that agent exists and is active
            # TODO: Add proper workspace validation when lead-workspace relationship is clarified
            pass
        
        return attrs
    
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
            'lead', 'agent', 'from_number', 'to_number', 'duration',
            'disconnection_reason', 'direction', 'status', 'appointment_datetime'
        ]
    
    def validate_duration(self, value):
        """Validate duration is not negative"""
        if value < 0:
            raise serializers.ValidationError("Duration cannot be negative")
        return value
    
    def validate(self, attrs):
        """Cross-field validation for appointment logic"""
        status = attrs.get('status')
        appointment_datetime = attrs.get('appointment_datetime')
        
        # Appointment datetime validation
        if status == 'appointment_scheduled':
            if not appointment_datetime:
                raise serializers.ValidationError({
                    'appointment_datetime': 'Appointment datetime is required when status is "appointment_scheduled"'
                })
        elif appointment_datetime:
            raise serializers.ValidationError({
                'appointment_datetime': 'Appointment datetime should only be set when status is "appointment_scheduled"'
            })
        
        return attrs


class OutboundCallSerializer(serializers.Serializer):
    """Serializer for making outbound calls via LiveKit"""
    
    # SIP Configuration
    sip_trunk_id = serializers.CharField(
        required=True,
        help_text="SIP trunk identifier for outbound calls"
    )
    from_number = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Caller ID number"
    )
    
    # Agent Selection
    agent_id = serializers.UUIDField(
        required=True,
        help_text="Agent UUID to make the call"
    )
    
    # Lead Selection
    lead_id = serializers.UUIDField(
        required=True,
        help_text="Lead UUID to call"
    )
    
    # Campaign Info
    campaign_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Campaign identifier"
    )
    
    # Optional call reason
    call_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        help_text="Reason for the call"
    )
    
    def validate_agent_id(self, value):
        """Validate agent exists and belongs to user's workspace"""
        try:
            agent = Agent.objects.get(agent_id=value)
            request = self.context.get('request')
            
            # Check if user has access to this agent
            if request and request.user:
                if not request.user.is_staff:
                    if request.user not in agent.workspace.users.all():
                        raise serializers.ValidationError(
                            "You can only use agents from your own workspace"
                        )
            
            return value
        except Agent.DoesNotExist:
            raise serializers.ValidationError("Agent not found")
    
    def validate_lead_id(self, value):
        """Validate lead exists"""
        if not Lead.objects.filter(id=value).exists():
            raise serializers.ValidationError("Lead not found")
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
    # New status analytics
    status_breakdown = serializers.DictField(read_only=True)
    appointments_scheduled = serializers.IntegerField(read_only=True)
    appointments_today = serializers.IntegerField(read_only=True)


class CallLogStatusAnalyticsSerializer(serializers.Serializer):
    """Serializer for call status analytics"""
    total_calls = serializers.IntegerField(read_only=True)
    status_breakdown = serializers.DictField(read_only=True)
    success_rate = serializers.FloatField(read_only=True)


class CallLogAgentPerformanceSerializer(serializers.Serializer):
    """Serializer for agent performance analytics"""
    agent_id = serializers.UUIDField(read_only=True)
    agent_workspace = serializers.CharField(read_only=True)
    total_calls = serializers.IntegerField(read_only=True)
    avg_duration = serializers.FloatField(read_only=True)
    status_breakdown = serializers.DictField(read_only=True)
    appointments_scheduled = serializers.IntegerField(read_only=True)


class CallLogAppointmentStatsSerializer(serializers.Serializer):
    """Serializer for appointment statistics"""
    total_appointments = serializers.IntegerField(read_only=True)
    appointments_today = serializers.IntegerField(read_only=True)
    appointments_this_week = serializers.IntegerField(read_only=True)
    appointments_this_month = serializers.IntegerField(read_only=True)
    upcoming_appointments = serializers.IntegerField(read_only=True)
    past_appointments = serializers.IntegerField(read_only=True) 