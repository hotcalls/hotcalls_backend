from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Agent, PhoneNumber, Voice, LeadFunnel


class PhoneNumberSerializer(serializers.ModelSerializer):
    """Serializer for PhoneNumber model"""
    
    class Meta:
        model = PhoneNumber
        fields = ['id', 'phonenumber', 'created_at', 'is_active']
        read_only_fields = ['id', 'created_at']


class AgentBasicSerializer(serializers.ModelSerializer):
    """Basic serializer for Agent with minimal fields"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    voice_external_id = serializers.SerializerMethodField()
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'name', 'status', 'workspace_name',
            'voice_external_id', 'language'
        ]
        read_only_fields = ['agent_id']
    
    @extend_schema_field(serializers.CharField)
    def get_voice_external_id(self, obj) -> str:
        """Get the voice external ID, handling null voice safely"""
        return obj.voice.voice_external_id if obj.voice else None


class LeadFunnelBasicSerializer(serializers.ModelSerializer):
    """Basic serializer for LeadFunnel to avoid circular imports"""
    
    class Meta:
        model = LeadFunnel
        fields = ['id', 'name', 'is_active']
        read_only_fields = ['id']


class AgentSerializer(serializers.ModelSerializer):
    """Serializer for Agent model"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    phone_number = PhoneNumberSerializer(read_only=True)
    phone_number_display = serializers.SerializerMethodField()
    # calendar_config_name removed - CalendarConfiguration no longer exists
    
    # NEW: Voice-related fields
    voice_provider = serializers.SerializerMethodField()
    voice_external_id = serializers.SerializerMethodField()
    
    # NEW: Lead funnel field
    lead_funnel = LeadFunnelBasicSerializer(read_only=True)
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'workspace', 'workspace_name', 
            # NEW FIELDS
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD (now FK to Voice)  
            'voice', 'voice_provider', 'voice_external_id',
            # LEAD FUNNEL FIELD
            'lead_funnel',
            # EXISTING FIELDS
            'language', 'retry_interval', 'max_retries', 'workdays', 'call_from', 'call_to',
            'character', 'prompt', 'phone_number', 'phone_number_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['agent_id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.CharField)
    def get_phone_number_display(self, obj) -> str:
        """Get the phone number assigned to this agent"""
        return obj.phone_number.phonenumber if obj.phone_number else 'No phone assigned'
    
    @extend_schema_field(serializers.CharField)
    def get_voice_provider(self, obj) -> str:
        """Get the voice provider, handling null voice safely"""
        return obj.voice.provider if obj.voice else None
    
    @extend_schema_field(serializers.CharField)
    def get_voice_external_id(self, obj) -> str:
        """Get the voice external ID, handling null voice safely"""
        return obj.voice.voice_external_id if obj.voice else None


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
            'language', 'retry_interval', 'max_retries', 'workdays', 'call_from', 'call_to', 
            'character', 'prompt', 'phone_number'
        ]
    
    def validate_workspace(self, value):
        """Validate user can create agents in this workspace"""
        request = self.context.get('request')
        
        if not request or not request.user:
            raise serializers.ValidationError("Authentication required")
        
        # Staff can create agents in any workspace
        if request.user.is_staff:
            return value
        
        # Regular users can only create agents in workspaces they belong to
        if request.user not in value.users.all():
            raise serializers.ValidationError(
                "You can only create agents in workspaces you belong to"
            )
        
        return value
    
    def validate_workdays(self, value):
        """Validate workdays contains only valid day names"""
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

        # Treat empty or None as all days
        if value in (None, []):
            return valid_days

        if not isinstance(value, list):
            raise serializers.ValidationError("Workdays must be a list")

        normalized = []
        for day in value:
            day_l = str(day).lower()
            if day_l not in valid_days:
                raise serializers.ValidationError(
                    f"'{day}' is not a valid weekday. Valid days are: {', '.join(valid_days)}"
                )
            normalized.append(day_l)

        return normalized
    
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

    def create(self, validated_data):
        """Create an agent and auto-assign workspace default phone if not provided."""
        phone = validated_data.get('phone_number')
        agent = Agent.objects.create(**validated_data)
        if phone is None:
            try:
                from core.services.phone_assignment import get_workspace_default_number
                default_phone = get_workspace_default_number(agent.workspace)
                if default_phone is not None:
                    agent.phone_number = default_phone
                    agent.save(update_fields=['phone_number'])
            except Exception:
                pass
        return agent


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating agents"""
    
    class Meta:
        model = Agent
        fields = [
            # NEW FIELDS  
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD
            'voice',
            # LEAD FUNNEL FIELD
            'lead_funnel',
            # EXISTING FIELDS
            'language', 'retry_interval', 'max_retries', 'workdays', 'call_from', 'call_to',
            'character', 'prompt'
        ]
    
    def validate_workdays(self, value):
        """Validate workdays contains only valid day names"""
        valid_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

        # Treat empty or None as all days
        if value in (None, []):
            return valid_days

        if not isinstance(value, list):
            raise serializers.ValidationError("Workdays must be a list")

        normalized = []
        for day in value:
            day_l = str(day).lower()
            if day_l not in valid_days:
                raise serializers.ValidationError(
                    f"'{day}' is not a valid weekday. Valid days are: {', '.join(valid_days)}"
                )
            normalized.append(day_l)

        return normalized
    
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


class AgentSendDocumentUploadSerializer(serializers.Serializer):
    """Serializer for uploading the agent's single PDF and optional defaults."""
    file = serializers.FileField(required=True)
    email_default_subject = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    email_default_body = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_file(self, f):
        # Only PDF, max 20MB
        max_bytes = 20 * 1024 * 1024
        content_type = getattr(f, 'content_type', '') or ''
        name_lower = (getattr(f, 'name', '') or '').lower()
        if not (content_type in ('application/pdf',) or name_lower.endswith('.pdf')):
            raise serializers.ValidationError('Only PDF files are allowed')
        if f.size and f.size > max_bytes:
            raise serializers.ValidationError('File exceeds 20 MB limit')
        return f


class AgentSendDocumentInfoSerializer(serializers.Serializer):
    """Serializer to expose current send-document status/defaults."""
    has_document = serializers.BooleanField()
    filename = serializers.CharField(allow_null=True)
    url = serializers.CharField(allow_null=True)
    email_default_subject = serializers.CharField(allow_null=True)
    email_default_body = serializers.CharField(allow_null=True)


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
    """Serializer for assigning a phone number to an agent"""
    phone_number_id = serializers.UUIDField(
        help_text="Phone number ID to assign to the agent"
    )
    
    def validate_phone_number_id(self, value):
        """Validate that the phone number ID exists and is active"""
        existing_number = PhoneNumber.objects.filter(id=value, is_active=True).first()
        if not existing_number:
            raise serializers.ValidationError("Phone number not found or is inactive")
        return value


class AgentConfigSerializer(serializers.ModelSerializer):
    """Serializer for agent configuration details"""
    workspace_name = serializers.CharField(source='workspace.workspace_name', read_only=True)
    phone_number = PhoneNumberSerializer(read_only=True)
    # calendar_config_id removed - CalendarConfiguration no longer exists
    # calendar_config_name removed - CalendarConfiguration no longer exists
    
    # NEW: Voice-related fields
    voice_provider = serializers.SerializerMethodField()
    voice_external_id = serializers.SerializerMethodField()
    
    # NEW: Lead funnel field
    lead_funnel = LeadFunnelBasicSerializer(read_only=True)
    
    class Meta:
        model = Agent
        fields = [
            'agent_id', 'workspace', 'workspace_name',
            # NEW FIELDS
            'name', 'status', 'greeting_inbound', 'greeting_outbound',
            # UPDATED VOICE FIELD
            'voice', 'voice_provider', 'voice_external_id',
            # LEAD FUNNEL FIELD
            'lead_funnel',
            # EXISTING FIELDS  
            'language', 'retry_interval', 'max_retries', 'workdays', 'call_from', 'call_to',
            'character', 'phone_number',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['agent_id', 'workspace', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.CharField)
    def get_voice_provider(self, obj) -> str:
        """Get the voice provider, handling null voice safely"""
        return obj.voice.provider if obj.voice else None
    
    @extend_schema_field(serializers.CharField)
    def get_voice_external_id(self, obj) -> str:
        """Get the voice external ID, handling null voice safely"""
        return obj.voice.voice_external_id if obj.voice else None
    
 