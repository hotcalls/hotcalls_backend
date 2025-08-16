from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import CallLog, Lead, Agent, CallTask
from django.utils import timezone


class CallLogSerializer(serializers.ModelSerializer):
    """Serializer for CallLog model"""
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    lead_surname = serializers.CharField(source='lead.surname', read_only=True)
    lead_email = serializers.CharField(source='lead.email', read_only=True)
    agent_workspace_name = serializers.CharField(source='agent.workspace.workspace_name', read_only=True)
    duration_formatted = serializers.SerializerMethodField()
    call_task_id = serializers.UUIDField(read_only=True)
    target_ref = serializers.CharField(read_only=True)
    
    class Meta:
        model = CallLog
        fields = [
            'id', 'lead', 'lead_name', 'lead_surname', 'lead_email', 
            'agent', 'agent_workspace_name',
            'timestamp', 'from_number', 'to_number', 'duration', 
            'duration_formatted', 'disconnection_reason', 'direction', 
            'appointment_datetime', 'call_task_id', 'target_ref', 'updated_at'
        ]
        read_only_fields = ['id', 'timestamp', 'updated_at']
    
    def validate_duration(self, value):
        """Validate duration is not negative"""
        if value < 0:
            raise serializers.ValidationError("Duration cannot be negative")
        return value
    
    def validate(self, attrs):
        """No cross-field validation needed now that status is removed."""
        return attrs
    
    @extend_schema_field(serializers.CharField)
    def get_duration_formatted(self, obj) -> str:
        """Format duration in minutes and seconds"""
        minutes = obj.duration // 60
        seconds = obj.duration % 60
        return f"{minutes}m {seconds}s"


class CallLogCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating call logs"""
    # Required linkage to currently running CallTask (not persisted)
    call_task_id = serializers.UUIDField(write_only=True, required=True, help_text="ID of running CallTask (required, not persisted)")
    # Duration will be computed from CallTask.created_at → now
    duration = serializers.IntegerField(read_only=True)
    # Target ref is copied from CallTask
    target_ref = serializers.CharField(read_only=True)
    
    class Meta:
        model = CallLog
        fields = [
            'lead', 'agent', 'from_number', 'to_number', 'duration',
            'disconnection_reason', 'direction', 'appointment_datetime',
            # Non-persisted request field
            'call_task_id',
            # Denormalized from CallTask
            'target_ref',
        ]
        extra_kwargs = {
            'lead': {'required': False, 'allow_null': True},
            'agent': {'required': False},
            'from_number': {'required': False},
            'to_number': {'required': False},
            'direction': {'required': False},
        }
    
    def validate_duration(self, value):
        """Validate duration is not negative"""
        if value < 0:
            raise serializers.ValidationError("Duration cannot be negative")
        return value
    
    def validate(self, attrs):
        """No cross-field validation needed for appointment datetime."""
        return attrs

    def create(self, validated_data):
        # Resolve CallTask and infer fields
        calltask_uuid = validated_data.pop('call_task_id', None)
        if not calltask_uuid:
            raise serializers.ValidationError({'call_task_id': 'call_task_id is required'})
        try:
            call_task = CallTask.objects.select_related('agent__phone_number', 'lead').get(id=calltask_uuid)
        except CallTask.DoesNotExist:
            raise serializers.ValidationError({'call_task_id': 'CallTask not found'})

        # Infer mandatory fields from CallTask
        agent = call_task.agent
        if not agent:
            raise serializers.ValidationError({'agent': 'CallTask has no agent'})

        # from_number must come from agent.phone_number.phonenumber
        if not getattr(agent, 'phone_number', None) or not getattr(agent.phone_number, 'phonenumber', None):
            raise serializers.ValidationError({'from_number': 'Agent has no phone number configured'})
        from_number = agent.phone_number.phonenumber

        # to_number comes from CallTask.phone
        to_number = call_task.phone
        if not to_number:
            raise serializers.ValidationError({'to_number': 'CallTask has no destination phone'})

        # direction defaults to outbound
        direction = validated_data.get('direction') or 'outbound'

        # Compute duration from CallTask.created_at to now
        now_ts = timezone.now()
        if not call_task.created_at:
            raise serializers.ValidationError({'call_task_id': 'CallTask has no created_at timestamp'})
        duration_seconds = int((now_ts - call_task.created_at).total_seconds())
        if duration_seconds < 0:
            duration_seconds = 0

        # Optional fields and overrides (only allow explicit override for direction per spec)
        disconnection_reason = validated_data.get('disconnection_reason')
        appointment_dt = validated_data.get('appointment_datetime')

        # Build instance data
        instance_data = {
            'call_task_id': call_task.id,
            'target_ref': call_task.target_ref,
            'agent': agent,
            'lead': call_task.lead,  # may be None
            'from_number': from_number,
            'to_number': to_number,
            'direction': direction,
            'duration': duration_seconds,
            'disconnection_reason': disconnection_reason,
            'appointment_datetime': appointment_dt,
        }

        # Create CallLog directly using model manager to avoid required field enforcement on missing inputs
        call_log = CallLog.objects.create(**instance_data)
        return call_log


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
            'prompt', 'calendar_configuration'
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
    # New: canonical target reference is required for creation
    target_ref = serializers.CharField(write_only=True, required=True, help_text="Canonical target (lead:<uuid> or test_user:<uuid>)")
    
    class Meta:
        model = CallTask
        fields = [
            'id', 'status', 'attempts', 'phone', 'next_call',
            'agent', 'agent_name', 'workspace', 'workspace_name',
            'lead', 'lead_name', 'target_ref',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'phone', 'lead', 'status', 'attempts', 'next_call']

    def validate_target_ref(self, value: str) -> str:
        """Allow only lead:<uuid> or test_user:<uuid> schemes."""
        if not value or ':' not in value:
            raise serializers.ValidationError("target_ref must be provided as 'lead:<uuid>' or 'test_user:<uuid>'")
        scheme = value.split(':', 1)[0]
        if scheme not in ('lead', 'test_user'):
            raise serializers.ValidationError("Unsupported target_ref scheme. Allowed: lead:<uuid>, test_user:<uuid>")
        return value


class CallTaskTriggerSerializer(serializers.Serializer):
    """Serializer for triggering a call task"""
    task_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True) 