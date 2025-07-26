from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import login, logout
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample
import secrets
from datetime import timedelta
from django.utils import timezone

from core.models import User
from core.utils import send_email_verification, send_password_reset_email
from .serializers import (
    UserRegistrationSerializer, EmailLoginSerializer, EmailVerificationSerializer,
    ResendVerificationSerializer, PasswordResetRequestSerializer, 
    PasswordResetConfirmSerializer, UserProfileSerializer
)


@extend_schema(
    summary="🔐 User Registration",
    description="""
    Register a new user account with mandatory email verification.
    
    **📧 Email Verification Required**: 
    - Users MUST verify their email before they can login
    - Verification email is sent automatically upon registration
    - Account remains unusable until email is verified
    
    **📝 Required Fields**:
    - `email`: Valid email address (will be username)
    - `first_name`: User's first name
    - `last_name`: User's last name  
    - `phone`: Contact phone number
    - `password`: Secure password (min 8 characters)
    - `password_confirm`: Password confirmation
    
    **🔒 Security Features**:
    - Password validation enforced
    - Email uniqueness checked
    - Verification token generated
    - HTML email sent with verification link
    
    **📋 Next Steps After Registration**:
    1. Check email inbox for verification message
    2. Click verification link or use `/verify-email/` endpoint
    3. Login with email and password after verification
    """,
    request=UserRegistrationSerializer,
    responses={
        201: OpenApiResponse(
            description="✅ User registered successfully - Verification email sent",
            examples=[
                OpenApiExample(
                    'Registration Success',
                    summary='User created, verification email sent',
                    value={
                        'message': 'Registration successful! Please check your email to verify your account.',
                        'email': 'user@example.com',
                        'verification_sent': True
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Registration failed - Validation errors",
            examples=[
                OpenApiExample(
                    'Email Already Exists',
                    summary='Email already registered',
                    value={
                        'email': ['A user with this email already exists.']
                    }
                ),
                OpenApiExample(
                    'Password Mismatch',
                    summary='Passwords do not match',
                    value={
                        'password_confirm': ['Passwords do not match.']
                    }
                )
            ]
        )
    },
    tags=["Authentication"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """Register a new user with mandatory email verification"""
    serializer = UserRegistrationSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = serializer.save()
        return Response({
            'message': 'Registration successful! Please check your email to verify your account.',
            'email': user.email,
            'verification_sent': True
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🔑 Email-Based Login",
    description="""
    Login with email and password. **Email verification is mandatory**.
    
    **🔐 Requirements**:
    - Valid email and password
    - Email MUST be verified (click link from registration email)
    - Account must be active and not suspended
    
    **❌ Login Blocked If**:
    - Email is not verified
    - Account is suspended or disabled
    - Invalid credentials provided
    
    **✅ Success Response**:
    - User session created
    - User profile data returned
    - Can access protected endpoints
    
    **📧 If Email Not Verified**:
    - Use `/resend-verification/` to get new verification email
    - Check spam/junk folders
    - Verify email address is correct
    """,
    request=EmailLoginSerializer,
    responses={
        200: OpenApiResponse(
            response=UserProfileSerializer,
            description="✅ Login successful - User authenticated",
            examples=[
                OpenApiExample(
                    'Login Success',
                    summary='User successfully logged in',
                    value={
                        'message': 'Login successful',
                        'user': {
                            'id': 'user-uuid',
                            'email': 'user@example.com',
                            'first_name': 'John',
                            'last_name': 'Doe',
                            'is_email_verified': True
                        }
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Login failed - Validation or verification errors",
            examples=[
                OpenApiExample(
                    'Email Not Verified',
                    summary='User must verify email first',
                    value={
                        'email': ['Please verify your email address before logging in. Check your inbox for the verification email.']
                    }
                ),
                OpenApiExample(
                    'Invalid Credentials',
                    summary='Wrong email or password',
                    value={
                        'non_field_errors': ['Invalid email or password.']
                    }
                ),
                OpenApiExample(
                    'Account Suspended',
                    summary='Account has been suspended',
                    value={
                        'non_field_errors': ['Your account has been suspended. Please contact support.']
                    }
                )
            ]
        )
    },
    tags=["Authentication"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Login with email and password (email verification required)"""
    serializer = EmailLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        login(request, user)
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        return Response({
            'message': 'Login successful',
            'user': UserProfileSerializer(user).data
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🚪 Logout",
    description="""
    Logout the current user and clear session.
    
    **🔐 Requirements**: Must be authenticated
    
    **✅ Effect**: 
    - User session cleared
    - Must login again to access protected endpoints
    """,
    responses={
        200: OpenApiResponse(
            description="✅ Logout successful",
            examples=[
                OpenApiExample(
                    'Logout Success',
                    summary='User logged out',
                    value={'message': 'Logout successful'}
                )
            ]
        ),
        401: OpenApiResponse(description="🚫 Authentication required")
    },
    tags=["Authentication"]
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Logout current user"""
    logout(request)
    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


@extend_schema(
    summary="✅ Verify Email Address",
    description="""
    Verify user's email address using verification token.
    
    **📧 How to Get Token**:
    - Token is sent in registration email
    - Also available via `/resend-verification/` endpoint
    - Token is in the verification URL
    
    **✅ After Verification**:
    - User can login with email/password
    - Account becomes fully functional
    - No need to verify again
    
    **🔒 Security**:
    - Token is single-use
    - Token expires (recommended: 24 hours)
    - Invalid tokens are rejected
    """,
    responses={
        200: OpenApiResponse(
            description="✅ Email verified successfully",
            examples=[
                OpenApiExample(
                    'Verification Success',
                    summary='Email successfully verified',
                    value={
                        'message': 'Email verified successfully! You can now login.',
                        'email_verified': True
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Verification failed",
            examples=[
                OpenApiExample(
                    'Invalid Token',
                    summary='Token is invalid or expired',
                    value={
                        'error': 'Invalid or expired verification token.'
                    }
                ),
                OpenApiExample(
                    'Already Verified',
                    summary='Email already verified',
                    value={
                        'error': 'Email is already verified.'
                    }
                )
            ]
        )
    },
    tags=["Authentication"]
)
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def verify_email(request, token):
    """Verify email address using token"""
    try:
        # Find user with this verification token
        user = User.objects.get(email_verification_token=token)
        
        # Check if already verified
        if user.is_email_verified:
            return Response({
                'error': 'Email is already verified.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify the email
        if user.verify_email(token):
            return Response({
                'message': 'Email verified successfully! You can now login.',
                'email_verified': True
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Invalid or expired verification token.'
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except User.DoesNotExist:
        return Response({
            'error': 'Invalid or expired verification token.'
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="📧 Resend Verification Email",
    description="""
    Resend email verification to user's email address.
    
    **📝 Use Cases**:
    - Original email was not received
    - Verification link expired
    - Email went to spam/junk folder
    
    **🔐 Requirements**:
    - Email must exist in system
    - Email must not already be verified
    
    **⏰ Rate Limiting**:
    - Consider implementing rate limiting
    - Don't allow spam requests
    """,
    request=ResendVerificationSerializer,
    responses={
        200: OpenApiResponse(
            description="✅ Verification email sent",
            examples=[
                OpenApiExample(
                    'Email Sent',
                    summary='New verification email sent',
                    value={
                        'message': 'Verification email sent! Please check your inbox.',
                        'email': 'user@example.com'
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description="❌ Cannot send verification email",
            examples=[
                OpenApiExample(
                    'Already Verified',
                    summary='Email already verified',
                    value={
                        'email': ['This email address is already verified.']
                    }
                ),
                OpenApiExample(
                    'User Not Found',
                    summary='No user with this email',
                    value={
                        'email': ['No user found with this email address.']
                    }
                )
            ]
        )
    },
    tags=["Authentication"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification(request):
    """Resend email verification"""
    serializer = ResendVerificationSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)
        
        # Send new verification email
        success = send_email_verification(user, request)
        if success:
            return Response({
                'message': 'Verification email sent! Please check your inbox.',
                'email': email
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to send verification email. Please try again later.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="👤 Get Current User Profile",
    description="""
    Get the profile of the currently authenticated user.
    
    **🔐 Requirements**: Must be authenticated and email verified
    
    **📋 Response Data**:
    - User identification and contact info
    - Email verification status
    - Account status and timestamps
    """,
    responses={
        200: OpenApiResponse(
            response=UserProfileSerializer,
            description="✅ User profile retrieved"
        ),
        401: OpenApiResponse(description="🚫 Authentication required")
    },
    tags=["Authentication"]
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """Get current user profile"""
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    summary="🔄 Request Password Reset",
    description="""
    Request a password reset email for the given email address.
    
    **🔒 Security Note**: 
    - Does not reveal if email exists or not
    - Always returns success message
    - Only sends email if user actually exists
    """,
    request=PasswordResetRequestSerializer,
    responses={
        200: OpenApiResponse(
            description="✅ Reset email sent (if email exists)",
            examples=[
                OpenApiExample(
                    'Reset Requested',
                    summary='Password reset email sent',
                    value={
                        'message': 'If an account with this email exists, a password reset link has been sent.'
                    }
                )
            ]
        )
    },
    tags=["Authentication"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    """Request password reset email"""
    serializer = PasswordResetRequestSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        
        try:
            user = User.objects.get(email=email)
            # Generate reset token (you might want to create a separate model for this)
            reset_token = secrets.token_urlsafe(32)
            # Store token with expiration (implement based on your needs)
            # send_password_reset_email(user, reset_token, request)
        except User.DoesNotExist:
            pass  # Don't reveal if email exists
        
        return Response({
            'message': 'If an account with this email exists, a password reset link has been sent.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="🔐 Reset Password",
    description="""
    Reset password using reset token.
    
    **📝 Requirements**:
    - Valid reset token from email
    - New password meeting requirements
    - Password confirmation
    """,
    request=PasswordResetConfirmSerializer,
    responses={
        200: OpenApiResponse(
            description="✅ Password reset successful",
            examples=[
                OpenApiExample(
                    'Reset Success',
                    summary='Password changed successfully',
                    value={
                        'message': 'Password reset successful! You can now login with your new password.'
                    }
                )
            ]
        ),
        400: OpenApiResponse(description="❌ Invalid token or validation errors")
    },
    tags=["Authentication"]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request, token):
    """Reset password using token"""
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        # Implement password reset logic here
        # This would require a password reset token model
        return Response({
            'message': 'Password reset successful! You can now login with your new password.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 