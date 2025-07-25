from rest_framework import serializers
from core.models import User, Blacklist


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 
            'phone', 'stripe_customer_id', 'status', 'social_id', 
            'social_provider', 'date_joined', 'last_login', 'is_active'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users"""
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email', 
            'phone', 'password', 'social_id', 'social_provider'
        ]
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating users"""
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone', 
            'stripe_customer_id', 'status', 'social_id', 'social_provider'
        ]


class BlacklistSerializer(serializers.ModelSerializer):
    """Serializer for Blacklist model"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Blacklist
        fields = [
            'id', 'user', 'user_username', 'user_email', 
            'reason', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BlacklistCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating blacklist entries"""
    
    class Meta:
        model = Blacklist
        fields = ['user', 'reason', 'status'] 