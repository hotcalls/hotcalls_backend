from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from core.models import Voice


class VoiceSerializer(serializers.ModelSerializer):
    """Serializer for Voice model"""
    agent_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Voice
        fields = [
            'id', 'voice_external_id', 'provider', 'name', 'gender',
            'tone', 'recommend', 'voice_sample', 'voice_picture', 'agent_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.IntegerField)
    def get_agent_count(self, obj) -> int:
        """Get the number of agents using this voice"""
        return obj.mapping_voice_agents.count()


class VoiceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating voices"""
    
    class Meta:
        model = Voice
        fields = ['voice_external_id', 'provider', 'name', 'gender', 'tone', 'recommend', 'voice_sample', 'voice_picture']
    
    def validate_provider(self, value):
        """Validate provider is from allowed choices"""
        valid_providers = ['openai', 'elevenlabs', 'google', 'azure', 'aws']
        
        if value.lower() not in valid_providers:
            raise serializers.ValidationError(
                f"Invalid provider '{value}'. Valid providers are: {', '.join(valid_providers)}"
            )
        
        return value.lower()
    
    def validate_voice_external_id(self, value):
        """Validate voice external ID format"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Voice external ID cannot be empty")
        
        if len(value) > 255:
            raise serializers.ValidationError("Voice external ID cannot exceed 255 characters")
        
        # Remove leading/trailing whitespace
        return value.strip()
    
    def validate_gender(self, value):
        """Validate gender choice"""
        valid_genders = ['male', 'female', 'neutral']
        if value.lower() not in valid_genders:
            raise serializers.ValidationError(
                f"Invalid gender '{value}'. Valid choices are: {', '.join(valid_genders)}"
            )
        return value.lower()

    def validate_name(self, value):
        """Validate voice name"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Voice name cannot be empty")
        if len(value) > 100:
            raise serializers.ValidationError("Voice name cannot exceed 100 characters")
        return value.strip()

    def validate_voice_picture(self, value):
        """Validate voice picture format"""
        if value:
            # Check file extension
            allowed_extensions = ['.png', '.jpg', '.jpeg']
            file_extension = value.name.lower().split('.')[-1]
            if f'.{file_extension}' not in allowed_extensions:
                raise serializers.ValidationError(
                    f"Invalid file format. Only PNG and JPG files are allowed."
                )
            
            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError(
                    "Voice picture file size cannot exceed 5MB."
                )
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        voice_external_id = attrs.get('voice_external_id')
        provider = attrs.get('provider')
        
        # Check for duplicate voice_external_id + provider combination
        if Voice.objects.filter(
            voice_external_id=voice_external_id,
            provider=provider
        ).exists():
            raise serializers.ValidationError(
                f"Voice with external ID '{voice_external_id}' already exists for provider '{provider}'"
            )
        
        return attrs


class VoiceUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating voices"""
    
    class Meta:
        model = Voice
        fields = ['voice_external_id', 'provider', 'name', 'gender', 'tone', 'recommend', 'voice_sample', 'voice_picture']
    
    def validate_provider(self, value):
        """Validate provider is from allowed choices"""
        valid_providers = ['openai', 'elevenlabs', 'google', 'azure', 'aws']
        
        if value.lower() not in valid_providers:
            raise serializers.ValidationError(
                f"Invalid provider '{value}'. Valid providers are: {', '.join(valid_providers)}"
            )
        
        return value.lower()
    
    def validate_voice_external_id(self, value):
        """Validate voice external ID format"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Voice external ID cannot be empty")
        
        if len(value) > 255:
            raise serializers.ValidationError("Voice external ID cannot exceed 255 characters")
        
        return value.strip()
    
    def validate_gender(self, value):
        """Validate gender choice"""
        valid_genders = ['male', 'female', 'neutral']
        if value.lower() not in valid_genders:
            raise serializers.ValidationError(
                f"Invalid gender '{value}'. Valid choices are: {', '.join(valid_genders)}"
            )
        return value.lower()

    def validate_name(self, value):
        """Validate voice name"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Voice name cannot be empty")
        if len(value) > 100:
            raise serializers.ValidationError("Voice name cannot exceed 100 characters")
        return value.strip()

    def validate_voice_picture(self, value):
        """Validate voice picture format"""
        if value:
            # Check file extension
            allowed_extensions = ['.png', '.jpg', '.jpeg']
            file_extension = value.name.lower().split('.')[-1]
            if f'.{file_extension}' not in allowed_extensions:
                raise serializers.ValidationError(
                    f"Invalid file format. Only PNG and JPG files are allowed."
                )
            
            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError(
                    "Voice picture file size cannot exceed 5MB."
                )
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation for updates"""
        voice_external_id = attrs.get('voice_external_id')
        provider = attrs.get('provider')
        
        # Skip validation if neither field is being updated
        if not voice_external_id and not provider:
            return attrs
        
        # Get current values if not provided
        if not voice_external_id:
            voice_external_id = self.instance.voice_external_id
        if not provider:
            provider = self.instance.provider
        
        # Check for duplicate (excluding current instance)
        duplicate_voice = Voice.objects.filter(
            voice_external_id=voice_external_id,
            provider=provider
        ).exclude(id=self.instance.id)
        
        if duplicate_voice.exists():
            raise serializers.ValidationError(
                f"Voice with external ID '{voice_external_id}' already exists for provider '{provider}'"
            )
        
        return attrs 