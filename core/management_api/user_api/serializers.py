from rest_framework import serializers
from core.models import User, Blacklist


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model with email-based authentication"""
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone', 
            'stripe_customer_id', 'status', 'social_id', 'social_provider',
            'is_email_verified', 'date_joined', 'last_login', 'is_active'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login', 'is_email_verified']


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new users via staff/admin endpoints.
    Note: Regular user registration should use auth API instead.
    """
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone', 
            'password', 'social_id', 'social_provider'
        ]
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        
        # SECURITY: Force all public registrations to be basic users only
        # Note: For regular users, they should use /api/auth/register/ instead
        validated_data['is_staff'] = False
        validated_data['is_superuser'] = False
        validated_data['is_active'] = True
        validated_data['status'] = 'active'
        validated_data['is_email_verified'] = False  # Must verify email
        
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user
    
    def validate(self, attrs):
        """Ensure no one can set privileged fields during registration"""
        # Remove any attempt to set privileged fields
        forbidden_fields = ['is_staff', 'is_superuser', 'is_active', 'status', 'groups', 'user_permissions', 'is_email_verified']
        for field in forbidden_fields:
            if field in attrs:
                attrs.pop(field)
        return attrs


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating users"""
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone', 
            'stripe_customer_id', 'status', 'social_id', 'social_provider'
        ]
        extra_kwargs = {
            'email': {'read_only': True}  # Email cannot be changed after registration
        }
    
    def validate(self, attrs):
        """Validate user update based on permissions"""
        request = self.context.get('request')
        if request and not request.user.is_staff:
            # Non-staff users cannot change status
            if 'status' in attrs:
                attrs.pop('status')
        
        # No one can set staff/superuser through this serializer
        forbidden_fields = ['is_staff', 'is_superuser', 'groups', 'user_permissions', 'is_email_verified']
        for field in forbidden_fields:
            if field in attrs:
                attrs.pop(field)
        
        return attrs


class BlacklistSerializer(serializers.ModelSerializer):
    """Serializer for Blacklist model"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Blacklist
        fields = [
            'id', 'user', 'user_email', 'user_name', 
            'reason', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        """Get user's full name"""
        return obj.user.get_full_name() if obj.user else ""


class UserStatusChangeSerializer(serializers.Serializer):
    """Serializer for changing user status"""
    status = serializers.ChoiceField(choices=User._meta.get_field('status').choices)


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """Admin-only serializer for creating users with elevated privileges"""
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone',
            'password', 'is_staff', 'is_superuser', 'is_active', 'status',
            'social_id', 'social_provider', 'is_email_verified'
        ]
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class BlacklistCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating blacklist entries"""
    
    class Meta:
        model = Blacklist
        fields = ['user', 'reason', 'status'] 