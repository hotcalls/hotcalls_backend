from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Agent, PhoneNumber, Workspace, CalendarConfiguration, Voice


class PhoneNumberSerializer(serializers.ModelSerializer):
    """Serializer for PhoneNumber model"""
    
    class Meta:
        model = PhoneNumber
        fields = ['id', 'phonenumber', 'created_at', 'is_active']
        read_only_fields = ['id', 'created_at']


class AgentSerializer(serializers.ModelSerializer):
    """Serializer for Agent model"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    phone_numbers = PhoneNumberSerializer(many=True, read_only=True)
    phone_number_count = serializers.SerializerMethodField()
    calendar_config_name = serializers.CharField(source='calendar_configuration.sub_calendar_id', read_only=True)
    
    # NEW: Voice-related fields
    voice_provider = serializers.CharField(source='voice.provider', read_only=True)
    voice_external_id = serializers.CharField(source='voice.voice_external_id', read_only=True)
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'workspace', 'workspace_name', 
            # NEW FIELDS
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD (now FK to Voice)  
            'voice', 'voice_provider', 'voice_external_id',
            # EXISTING FIELDS
            'language', 'retry_interval', 'workdays', 'call_from', 'call_to',
            'character', 'prompt', 'config_id', 'phone_numbers', 'phone_number_count',
            'calendar_configuration', 'calendar_config_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['agent_id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.IntegerField)
    def get_phone_number_count(self, obj) -> int:
        """Get the number of phone numbers assigned to this agent"""
        return obj.phone_numbers.count()


class AgentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating agents"""
    
    class Meta:
        model = Agent
        fields = [
            'workspace', 
            # NEW FIELDS
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD
            'voice', 
            # EXISTING FIELDS
            'language', 'retry_interval', 'workdays', 'call_from', 'call_to', 
            'character', 'prompt', 'config_id', 'calendar_configuration'
        ]
    
    def validate_workdays(self, value):
        """Validate workdays contains only valid day names"""
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        if not isinstance(value, list):
            raise serializers.ValidationError("Workdays must be a list")
        
        for day in value:
            if day.lower() not in valid_days:
                raise serializers.ValidationError(
                    f"'{day}' is not a valid weekday. Valid days are: {', '.join(valid_days)}"
                )
        
        return value
    
    def validate_name(self, value):
        """Validate agent name"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Agent name cannot be empty")
        
        if len(value) > 255:
            raise serializers.ValidationError("Agent name cannot exceed 255 characters")
        
        return value.strip()
    
    def validate_voice(self, value):
        """Validate voice exists and is active"""
        if value is None:
            return value  # Allow None for voice
        
        if not Voice.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Selected voice does not exist")
        
        return value


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating agents"""
    
    class Meta:
        model = Agent
        fields = [
            # NEW FIELDS  
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD
            'voice',
            # EXISTING FIELDS
            'language', 'retry_interval', 'workdays', 'call_from', 'call_to',
            'character', 'prompt', 'config_id', 'calendar_configuration'
        ]
    
    def validate_workdays(self, value):
        """Validate workdays contains only valid day names"""
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        if not isinstance(value, list):
            raise serializers.ValidationError("Workdays must be a list")
        
        for day in value:
            if day.lower() not in valid_days:
                raise serializers.ValidationError(
                    f"'{day}' is not a valid weekday. Valid days are: {', '.join(valid_days)}"
                )
        
        return value
    
    def validate_name(self, value):
        """Validate agent name"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Agent name cannot be empty")
        
        if len(value) > 255:
            raise serializers.ValidationError("Agent name cannot exceed 255 characters")
        
        return value.strip()
    
    def validate_voice(self, value):
        """Validate voice exists and is active"""
        if value is None:
            return value  # Allow None for voice
        
        if not Voice.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Selected voice does not exist")
        
        return value


class PhoneNumberCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating phone numbers"""
    
    class Meta:
        model = PhoneNumber
        fields = ['phonenumber']
    
    def validate_phonenumber(self, value):
        """Validate phone number format"""
        # Remove any non-digit characters for validation
        cleaned = ''.join(filter(str.isdigit, value))
        if len(cleaned) < 10:
            raise serializers.ValidationError("Phone number must contain at least 10 digits")
        return value


class AgentPhoneAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning/removing phone numbers to/from agents"""
    phone_number_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="List of phone number IDs to assign/remove"
    )
    
    def validate_phone_number_ids(self, value):
        """Validate that all phone number IDs exist and are active"""
        existing_numbers = PhoneNumber.objects.filter(id__in=value, is_active=True)
        if len(existing_numbers) != len(value):
            missing_ids = set(value) - set(existing_numbers.values_list('id', flat=True))
            raise serializers.ValidationError(
                f"The following phone number IDs do not exist or are inactive: {list(missing_ids)}"
            )
        return value


class AgentConfigSerializer(serializers.ModelSerializer):
    """Serializer for agent configuration details"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    phone_numbers = serializers.SerializerMethodField()
    calendar_config_id = serializers.CharField(source='calendar_configuration.id', read_only=True)
    calendar_config_name = serializers.CharField(source='calendar_configuration.sub_calendar_id', read_only=True)
    
    # NEW: Voice-related fields
    voice_provider = serializers.CharField(source='voice.provider', read_only=True)
    voice_external_id = serializers.CharField(source='voice.voice_external_id', read_only=True)
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'workspace', 'workspace_name',
            # NEW FIELDS
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD
            'voice', 'voice_provider', 'voice_external_id',
            # EXISTING FIELDS  
            'language', 'retry_interval', 'workdays', 'call_from', 'call_to',
            'character', 'config_id', 'phone_numbers', 'calendar_configuration',
            'calendar_config_id', 'calendar_config_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['agent_id', 'workspace', 'created_at', 'updated_at']
    
    def get_phone_numbers(self, obj):
        """Return phone numbers as strings instead of objects"""
        return [pn.phonenumber for pn in obj.phone_numbers.all()] 