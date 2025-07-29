from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth import login, logout
from django.http import JsonResponse
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
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Login with email and password (email verification required)"""
    if request.method == 'GET':
        # For GET requests, just return a message instead of an error
        return Response({
            'message': 'This is the login endpoint. Send POST request with email and password to login.'
        }, status=status.HTTP_200_OK)
    
    # POST request - handle login
    serializer = EmailLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        login(request, user)
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        # Get the first workspace
        workspace = user.mapping_user_workspaces.first()
        
        # Check if workspace has active subscription
        has_active_subscription = False
        needs_payment = False
        
        if workspace:
            # Check subscription status
            if workspace.subscription_status in ['active', 'trial']:
                has_active_subscription = True
            else:
                needs_payment = True
                
            # If there's a Stripe subscription, verify with Stripe
            if workspace.stripe_subscription_id:
                try:
                    import stripe
                    from django.conf import settings
                    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
                    
                    subscription = stripe.Subscription.retrieve(workspace.stripe_subscription_id)
                    if subscription.status == 'active':
                        has_active_subscription = True
                        needs_payment = False
                    else:
                        has_active_subscription = False
                        needs_payment = True
                except:
                    pass  # Use database values if Stripe fails
        
        # Return user data with subscription info
        return Response({
            'user': UserProfileSerializer(user).data,
            'workspace_id': str(workspace.id) if workspace else None,
            'has_active_subscription': has_active_subscription,
            'needs_payment': needs_payment,
            'subscription_status': workspace.subscription_status if workspace else None,
            'message': 'Login successful' if has_active_subscription else 'Payment required'
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
            return render(request, 'auth/verification_error.html', {
                'error_message': 'This email address is already verified.'
            })
        
        # Verify the email
        if user.verify_email(token):
            # Create initial workspace for the user if they don't have any
            from core.models import Workspace
            if not Workspace.objects.filter(users=user).exists():
                workspace = Workspace.objects.create(
                    workspace_name=f"{user.first_name or user.email.split('@')[0]}'s Workspace"
                )
                workspace.users.add(user)
                workspace.save()
            
            return render(request, 'auth/verification_success.html', {
                'email': user.email
            })
        else:
            return render(request, 'auth/verification_error.html', {
                'error_message': 'The verification link is invalid or has expired.'
            })
            
    except User.DoesNotExist:
        return render(request, 'auth/verification_error.html', {
            'error_message': 'The verification link is invalid or has expired.'
        })


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
@extend_schema_view(
    get=extend_schema(
        summary="📝 Password Reset Form",
        description="""
        Show password reset request form (HTML) or return instructions (API).
        
        **📝 GET Request**: Display password reset form for browsers
        **📨 Use Case**: User visits link to request password reset
        """,
        responses={
            200: OpenApiResponse(description="✅ Password reset form displayed or instructions provided")
        },
        tags=["Authentication"]
    ),
    post=extend_schema(
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
    ),
)
class PasswordResetRequestView(APIView):
    """Handle password reset requests with both HTML and API support"""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    
    def is_browser_request(self, request):
        """Check if request is from browser (HTML) or API (JSON)"""
        accept_header = request.META.get('HTTP_ACCEPT', '')
        return 'text/html' in accept_header
    
    def get(self, request):
        """GET request - Show password reset request form"""
        if self.is_browser_request(request):
            return render(request, 'auth/password_reset_request.html', {
                'email': '',
                'error': None,
                'success': None
            })
        else:
            return JsonResponse({
                'message': 'Send POST request with email to request password reset.'
            })
    
    def post(self, request):
        """POST request - Process password reset"""
        # Handle both form data and JSON data
        if request.content_type == 'application/x-www-form-urlencoded' or 'multipart/form-data' in request.content_type:
            # HTML form submission
            email = request.POST.get('email')
            
            if not email:
                return render(request, 'auth/password_reset_request.html', {
                    'error': 'Email address is required.',
                    'email': '',
                    'success': None
                })
            
            try:
                user = User.objects.get(email=email)
                # Generate and store reset token
                reset_token = user.generate_password_reset_token()
                # Send password reset email
                send_password_reset_email(user, reset_token, request)
            except User.DoesNotExist:
                pass  # Don't reveal if email exists
            
            return render(request, 'auth/password_reset_request.html', {
                'success': 'If an account with this email exists, a password reset link has been sent to your email.',
                'email': email or '',
                'error': None
            })
        else:
            # JSON API request - use DRF's request.data to avoid body parsing conflicts
            serializer = PasswordResetRequestSerializer(data=request.data)
            if serializer.is_valid():
                email = serializer.validated_data['email']
                
                try:
                    user = User.objects.get(email=email)
                    # Generate and store reset token
                    reset_token = user.generate_password_reset_token()
                    # Send password reset email
                    send_password_reset_email(user, reset_token, request)
                except User.DoesNotExist:
                    pass  # Don't reveal if email exists
                
                return JsonResponse({
                    'message': 'If an account with this email exists, a password reset link has been sent.'
                })
            
            return JsonResponse(serializer.errors, status=400)




@extend_schema_view(
    get=extend_schema(
        summary="🔍 Validate Reset Token",
        description="""
        Validate password reset token and show form (HTML) or return validation (API).
        
        **📝 GET Request**: Validate token and show password reset form for browsers
        **🔑 Token Validation**: Checks if token is valid and not expired (24 hours)
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Token valid - form displayed or validation confirmed",
                examples=[
                    OpenApiExample(
                        'Token Valid',
                        summary='Token is valid and ready for password reset',
                        value={
                            'message': 'Valid reset token. You can now set a new password.',
                            'token': 'abc123...',
                            'user_email': 'user@example.com'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Invalid or expired token")
        },
        tags=["Authentication"]
    ),
    post=extend_schema(
        summary="🔐 Reset Password",
        description="""
        Reset password using validated token.
        
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
    ),
)
class PasswordResetConfirmView(APIView):
    """Handle password reset confirmation with both HTML and API support"""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    

    
    def is_browser_request(self, request):
        """Check if request is from browser (HTML) or API (JSON)"""
        accept_header = request.META.get('HTTP_ACCEPT', '')
        return 'text/html' in accept_header
    
    def get(self, request, token):
        """GET request - Validate token and show form"""
        try:
            user = User.objects.get(password_reset_token=token)
            # Check if token is valid and not expired
            if user.verify_password_reset_token(token):
                if self.is_browser_request(request):
                    # Return HTML form for browser requests
                    return render(request, 'auth/password_reset_form.html', {
                        'token': token,
                        'user_email': user.email
                    })
                else:
                    # Return JSON for API requests
                    return JsonResponse({
                        'message': 'Valid reset token. You can now set a new password.',
                        'token': token,
                        'user_email': user.email
                    })
            else:
                error_msg = 'Invalid or expired reset token.'
                if self.is_browser_request(request):
                    return render(request, 'auth/password_reset_error.html', {
                        'error': error_msg
                    })
                else:
                    return JsonResponse({'error': error_msg}, status=400)
        except User.DoesNotExist:
            error_msg = 'Invalid reset token.'
            if self.is_browser_request(request):
                return render(request, 'auth/password_reset_error.html', {
                    'error': error_msg
                })
            else:
                return JsonResponse({'error': error_msg}, status=400)
    
    def post(self, request, token):
        """POST request - Actually reset the password"""
        # Handle both form data and JSON data
        if request.content_type == 'application/x-www-form-urlencoded' or 'multipart/form-data' in request.content_type:
            # HTML form submission
            password = request.POST.get('password')
            password_confirm = request.POST.get('password_confirm')
            
            # Validate passwords match
            if password != password_confirm:
                # Get user email for template
                try:
                    user = User.objects.get(password_reset_token=token)
                    user_email = user.email
                except User.DoesNotExist:
                    user_email = ''
                return render(request, 'auth/password_reset_form.html', {
                    'token': token,
                    'error': 'Passwords do not match.',
                    'user_email': user_email
                })
            
            # Validate password strength
            try:
                validate_password(password)
            except ValidationError as e:
                # Get user email for template
                try:
                    user = User.objects.get(password_reset_token=token)
                    user_email = user.email
                except User.DoesNotExist:
                    user_email = ''
                return render(request, 'auth/password_reset_form.html', {
                    'token': token,
                    'error': '; '.join(e.messages),
                    'user_email': user_email
                })
            
            # Find user and reset password
            try:
                user = User.objects.get(password_reset_token=token)
                if user.reset_password_with_token(token, password):
                    return render(request, 'auth/password_reset_success.html')
                else:
                    return render(request, 'auth/password_reset_error.html', {
                        'error': 'Invalid or expired reset token.'
                    })
            except User.DoesNotExist:
                return render(request, 'auth/password_reset_error.html', {
                    'error': 'Invalid reset token.'
                })
        else:
            # JSON API request - use DRF's request.data to avoid body parsing conflicts
            serializer = PasswordResetConfirmSerializer(data=request.data)
            if serializer.is_valid():
                password = serializer.validated_data['password']
                
                # Find user with this reset token
                try:
                    user = User.objects.get(password_reset_token=token)
                    # Reset password using the token
                    if user.reset_password_with_token(token, password):
                        return JsonResponse({
                            'message': 'Password reset successful! You can now login with your new password.'
                        })
                    else:
                        return JsonResponse({
                            'error': 'Invalid or expired reset token.'
                        }, status=400)
                except User.DoesNotExist:
                    return JsonResponse({
                        'error': 'Invalid reset token.'
                    }, status=400)
            
            return JsonResponse(serializer.errors, status=400)

 