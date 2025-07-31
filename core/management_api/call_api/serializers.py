from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import CallLog, Lead, Agent, CallTask
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime


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
    
    # Phone number to call (required)
    phone = serializers.CharField(
        required=True,
        help_text="Phone number to call (required)"
    )
    
    # Agent Selection (required)
    agent_id = serializers.UUIDField(
        required=True,
        help_text="Agent UUID to make the call (required)"
    )
    
    # Lead Selection (optional)
    lead_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Lead UUID to associate with call (optional)"
    )
    
    # NEW: Dynamic agent configuration override (optional)
    agent_config = serializers.DictField(
        required=False,
        allow_null=True,
        default=dict,
        help_text="Optional: Override agent configuration fields for this call"
    )
    
    # NEW: Lead data including custom fields (optional)
    lead_data = serializers.DictField(
        required=False,
        allow_null=True,
        default=dict,
        help_text="Optional: Lead information with custom fields for personalization"
    )
    
    # NEW: Custom greeting template (optional)
    custom_greeting = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=1000,
        help_text="Optional: Custom greeting with placeholders like {name}, {topic}, etc."
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
        """Validate lead exists if provided"""
        if value and not Lead.objects.filter(id=value).exists():
            raise serializers.ValidationError("Lead not found")
        return value
    
    def validate_phone(self, value):
        """Basic phone validation"""
        if not value:
            raise serializers.ValidationError("Phone number is required")
        # Remove spaces and validate it starts with +
        cleaned = value.replace(" ", "")
        if not cleaned.startswith("+"):
            raise serializers.ValidationError("Phone number must start with + and country code")
        return cleaned
    
    def validate_agent_config(self, value):
        """Validate agent_config contains only allowed fields"""
        if not value:
            return value
        
        # Define allowed fields based on Agent model
        allowed_fields = {
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            'voice', 'language', 'retry_interval', 'max_retries',
            'workdays', 'call_from', 'call_to', 'character', 
            'prompt', 'config_id', 'calendar_configuration'
        }
        
        # Check for invalid fields
        invalid_fields = set(value.keys()) - allowed_fields
        if invalid_fields:
            raise serializers.ValidationError(
                f"Invalid agent configuration fields: {', '.join(invalid_fields)}. "
                f"Allowed fields are: {', '.join(sorted(allowed_fields))}"
            )
        
        # Validate specific field types if provided
        if 'workdays' in value and value['workdays'] is not None:
            if not isinstance(value['workdays'], list):
                raise serializers.ValidationError(
                    {"workdays": "Must be a list of weekday names"}
                )
            valid_days = {'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'}
            for day in value['workdays']:
                if day.lower() not in valid_days:
                    raise serializers.ValidationError(
                        {"workdays": f"'{day}' is not a valid weekday"}
                    )
        
        if 'retry_interval' in value and value['retry_interval'] is not None:
            if not isinstance(value['retry_interval'], int) or value['retry_interval'] < 0:
                raise serializers.ValidationError(
                    {"retry_interval": "Must be a positive integer"}
                )
                
        if 'max_retries' in value and value['max_retries'] is not None:
            if not isinstance(value['max_retries'], int) or value['max_retries'] < 0:
                raise serializers.ValidationError(
                    {"max_retries": "Must be a positive integer"}
                )
        
        return value
    
    def validate_lead_data(self, value):
        """Validate lead_data structure"""
        if not value:
            return value
            
        # Ensure custom_fields is a dict if provided
        if 'custom_fields' in value and value['custom_fields'] is not None:
            if not isinstance(value['custom_fields'], dict):
                raise serializers.ValidationError(
                    {"custom_fields": "Must be a dictionary of key-value pairs"}
                )
        
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


class TestCallSerializer(serializers.Serializer):
    """Serializer for making test calls with only Agent ID"""
    
    agent_id = serializers.UUIDField(
        required=True,
        help_text="Agent UUID to make the test call (required)"
    )
    
    def validate_agent_id(self, value):
        """Validate agent exists and belongs to user's workspace"""
        try:
            agent = Agent.objects.get(agent_id=value)
            request = self.context.get('request')
            
            # Check if user has access to this agent
            if request and request.user:
                if not request.user.is_superuser:
                    if request.user not in agent.workspace.users.all():
                        raise serializers.ValidationError(
                            "You can only use agents from your own workspace"
                        )
            
            return value
        except Agent.DoesNotExist:
            raise serializers.ValidationError("Agent not found") 


class CallTaskSerializer(serializers.ModelSerializer):
    """Serializer for CallTask model"""
    agent_name = serializers.CharField(source='agent.name', read_only=True)
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    
    class Meta:
        model = CallTask
        fields = [
            'id', 'status', 'attempts', 'phone', 'next_call',
            'agent', 'agent_name', 'workspace', 'workspace_name',
            'lead', 'lead_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CallTaskTriggerSerializer(serializers.Serializer):
    """Serializer for triggering a call task"""
    task_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True) 