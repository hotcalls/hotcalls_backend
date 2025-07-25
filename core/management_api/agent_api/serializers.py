from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Agent, PhoneNumber, Workspace, CalendarConfiguration


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
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'workspace', 'workspace_name', 'greeting', 'voice', 
            'language', 'retry_interval', 'workdays', 'call_from', 'call_to',
            'character', 'config_id', 'phone_numbers', 'phone_number_count',
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
            'workspace', 'greeting', 'voice', 'language', 'retry_interval',
            'workdays', 'call_from', 'call_to', 'character', 'config_id',
            'calendar_configuration'
        ]


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating agents"""
    
    class Meta:
        model = Agent
        fields = [
            'greeting', 'voice', 'language', 'retry_interval',
            'workdays', 'call_from', 'call_to', 'character', 'config_id',
            'calendar_configuration'
        ]


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
    phone_numbers = PhoneNumberSerializer(many=True, read_only=True)
    calendar_config_id = serializers.CharField(source='calendar_configuration.id', read_only=True)
    calendar_config_name = serializers.CharField(source='calendar_configuration.sub_calendar_id', read_only=True)
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'workspace', 'workspace_name', 'greeting', 'voice', 
            'language', 'retry_interval', 'workdays', 'call_from', 'call_to',
            'character', 'config_id', 'phone_numbers', 'calendar_configuration',
            'calendar_config_id', 'calendar_config_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['agent_id', 'workspace', 'created_at', 'updated_at'] 