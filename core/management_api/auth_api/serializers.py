from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from core.models import User
from core.utils import send_email_verification


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration with mandatory email verification"""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone', 
            'password', 'password_confirm'
        ]
    
    def validate(self, attrs):
        """Validate password confirmation and email uniqueness"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match.'
            })
        
        # Check if email already exists
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({
                'email': 'A user with this email already exists.'
            })
        
        return attrs
    
    def create(self, validated_data):
        """Create user with email verification required"""
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Create user but set email as unverified
        user = User.objects.create_user(
            password=password,
            is_email_verified=False,  # Must verify email
            **validated_data
        )
        
        # Send verification email
        send_email_verification(user, self.context.get('request'))
        
        return user


class EmailLoginSerializer(serializers.Serializer):
    """Serializer for email-based login with email verification check"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        """Authenticate user and check email verification"""
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            # Check if user exists
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'non_field_errors': ['Invalid email or password.']
                })
            
            # Check if email is verified
            if not user.is_email_verified:
                raise serializers.ValidationError({
                    'email': 'Please verify your email address before logging in. Check your inbox for the verification email.'
                })
            
            # Check if user can login (active, etc.)
            if not user.can_login():
                if user.status != 'active':
                    raise serializers.ValidationError({
                        'non_field_errors': ['Your account has been suspended. Please contact support.']
                    })
                if not user.is_active:
                    raise serializers.ValidationError({
                        'non_field_errors': ['Your account has been deactivated. Please contact support.']
                    })
            
            # Authenticate user
            user = authenticate(email=email, password=password)
            if not user:
                raise serializers.ValidationError({
                    'non_field_errors': ['Invalid email or password.']
                })
            
            attrs['user'] = user
        else:
            raise serializers.ValidationError({
                'non_field_errors': ['Must include email and password.']
            })
        
        return attrs


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification"""
    token = serializers.CharField()
    
    def validate_token(self, value):
        """Validate verification token"""
        if not value:
            raise serializers.ValidationError('Verification token is required.')
        return value


class ResendVerificationSerializer(serializers.Serializer):
    """Serializer for resending verification email"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if user exists and needs verification"""
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError('No user found with this email address.')
        
        if user.is_email_verified:
            raise serializers.ValidationError('This email address is already verified.')
        
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if user exists"""
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            # Don't reveal if email exists or not for security
            pass
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation"""
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        """Validate password confirmation"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match.'
            })
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile display"""
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'is_email_verified', 'date_joined', 'last_login', 
            'status', 'is_active'
        ]
        read_only_fields = [
            'id', 'email', 'is_email_verified', 'date_joined', 
            'last_login', 'status', 'is_active'
        ] 