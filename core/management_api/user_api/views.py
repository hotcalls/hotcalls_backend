from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import User, Blacklist
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    UserStatusChangeSerializer, AdminUserCreateSerializer,
    BlacklistSerializer, BlacklistCreateSerializer
)
from .filters import UserFilter, BlacklistFilter
from .permissions import UserPermission, BlacklistPermission


@extend_schema_view(
    list=extend_schema(
        summary="👤 List users",
        description="""
        Retrieve users based on your permission level and role.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see their own profile (filtered response)
        - **Staff Members**: Can view all users in the system
        - **Superusers**: Full access to all user data
        - **⚠️ Email Verification Required**: Must have verified email to access
        
        **📊 Response Filtering**:
        - Regular users receive only 1 result (themselves)
        - Staff/Superusers receive all users with pagination
        
        **🎯 Use Cases**:
        - User profile management
        - Staff user administration
        - System user overview
        
        **📧 Note**: This API now works with email-based authentication instead of username
        """,
        responses={
            200: OpenApiResponse(
                response=UserSerializer(many=True),
                description="Successfully retrieved users based on permission level",
                examples=[
                    OpenApiExample(
                        'Regular User Response',
                        summary='Regular user sees only own profile',
                        description='Regular users are filtered to see only their own user data',
                        value={
                            'count': 1,
                            'next': None,
                            'previous': None,
                            'results': [{
                                'id': 'user-uuid-here',
                                'email': 'current_user@example.com',
                                'first_name': 'John',
                                'last_name': 'Doe',
                                'phone': '+1234567890',
                                'status': 'active',
                                'is_email_verified': True
                            }]
                        }
                    ),
                    OpenApiExample(
                        'Staff User Response',
                        summary='Staff sees all users',
                        description='Staff members can view all user profiles in the system',
                        value={
                            'count': 150,
                            'next': 'http://localhost:8001/api/users/users/?page=2',
                            'previous': None,
                            'results': [
                                {'id': 'uuid1', 'email': 'user1@example.com', 'status': 'active', 'is_email_verified': True},
                                {'id': 'uuid2', 'email': 'user2@example.com', 'status': 'suspended', 'is_email_verified': False}
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access user data"),
            403: OpenApiResponse(description="🚫 Permission denied or email not verified")
        },
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="➕ Create new user (Admin)",
        description="""
        Create a new user account via admin interface. 
        
        **⚠️ Note**: Regular users should use `/api/auth/register/` instead for proper email verification flow.
        
        **🔐 Permission Requirements**: 
        - **Staff/Admin Access**: Only staff and admin can create users via this endpoint
        - **Email Verification Required**: Creator must have verified email
        
        **📝 Required Fields**:
        - `email`: Valid email address (will be username)
        - `password`: Secure password min 8 characters
        - `first_name`, `last_name`: User's name
        - `phone`: Contact phone number
        
        **⚙️ Optional Fields**:
        - `social_id`, `social_provider`: For social media login integration
        
        **🔒 Security Notes**:
        - Password is automatically hashed
        - New users created with `is_email_verified=False` by default
        - Created users must still verify their email to login
        """,
        request=UserCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=UserSerializer,
                description="✅ User account created successfully",
                examples=[
                    OpenApiExample(
                        'Successful Creation',
                        summary='New user account created by admin',
                        description='User successfully created but must still verify email',
                        value={
                            'id': 'new-user-uuid',
                            'email': 'newuser@example.com',
                            'first_name': 'Jane',
                            'last_name': 'Smith',
                            'phone': '+1234567890',
                            'status': 'active',
                            'is_active': True,
                            'is_email_verified': False,
                            'date_joined': '2024-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="❌ Validation error - Check required fields and format",
                examples=[
                    OpenApiExample(
                        'Validation Error',
                        summary='Invalid input data',
                        value={
                            'email': ['Enter a valid email address.'],
                            'password': ['Ensure this field has at least 8 characters.']
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Staff access required or email not verified")
        },
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get user details",
        description="""
        Retrieve detailed information about a specific user.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only access their own profile
        - **Staff Members**: Can access any user's profile  
        - **Superusers**: Full access to any user's profile
        - **⚠️ Email Verification Required**: Must have verified email
        
        **🛡️ Access Control**:
        - Users attempting to access other profiles get 404 (not 403 for security)
        - Staff can see all user details including email verification status
        - Response includes email-based authentication fields
        """,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="✅ User details retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Cannot access other user's profile"),
            404: OpenApiResponse(description="🚫 User not found or access denied")
        },
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="✏️ Update user (full)",
        description="""
        Update all fields of a user account.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only update their own profile
        - **Staff Members**: Can update any user's profile
        - **Superusers**: Can update any user's profile
        - **⚠️ Email Verification Required**: Must have verified email
        
        **🔄 Update Scope**:
        - Replaces all editable fields with new values
        - Cannot modify: `id`, `email`, `date_joined`, `last_login`, `is_email_verified`
        - Staff can modify: `status`, admin flags
        - Users can modify: personal information only
        
        **📧 Email Changes**: Email addresses cannot be changed after registration for security
        """,
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="✅ User updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Cannot edit other user's profile"),
            404: OpenApiResponse(description="🚫 User not found")
        },
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Update user (partial)",
        description="""
        Update specific fields of a user account.
        
        **🔐 Permission Requirements**: Same as full update
        - **Regular Users**: Own profile only
        - **Staff/Superuser**: Any user profile
        - **⚠️ Email Verification Required**: Must have verified email
        
        **🎯 Partial Update Benefits**:
        - Only send fields you want to change
        - Other fields remain unchanged
        - More efficient for single field updates
        """,
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="✅ User updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 User not found")
        },
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete user",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete a user account.**
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access to delete operations
        - **❌ Staff Members**: Cannot delete user accounts
        - **✅ Superuser ONLY**: Can delete any user account
        - **⚠️ Email Verification Required**: Superuser must have verified email
        
        **💥 Consequences**:
        - User account permanently removed
        - All associated data may be affected
        - Cannot be undone - consider deactivation instead
        
        **🛡️ Safety Recommendations**:
        - Use status change to 'suspended' instead of deletion
        - Ensure data backup before deletion
        - Consider impact on related workspace/agent data
        """,
        responses={
            204: OpenApiResponse(description="✅ User deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Only superusers can delete users",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        summary='Non-superuser attempted deletion',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 User not found")
        },
        tags=["User Management"]
    ),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    🔐 **User Management ViewSet with Email-Based Authentication**
    
    Provides comprehensive user management with email-based authentication:
    - **📧 Email as Username**: Users login with email instead of username
    - **✅ Email Verification Required**: All users must verify email to access APIs
    - **👤 Regular Users**: Self-management only (with verified email)
    - **👔 Staff**: Full user administration (with verified email)
    - **🔧 Superusers**: Complete system control (auto-verified email)
    """
    queryset = User.objects.all()
    permission_classes = [UserPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilter
    search_fields = ['email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['email', 'date_joined', 'last_login']
    ordering = ['-date_joined']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            # UserCreateSerializer enforces basic user creation only
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_permissions(self):
        """Return appropriate permissions based on action"""
        if self.action == 'create':
            # User creation via this endpoint requires authentication
            # Regular users should use /api/auth/register/ instead
            return [IsAuthenticated()]
        return super().get_permissions()
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return User.objects.all()
        else:
            # Regular users can only see their own profile
            return User.objects.filter(id=user.id)
    
    @extend_schema(
        summary="👤 Get current user profile",
        description="""
        Get the profile of the currently authenticated user.
        
        **🔐 Permission Requirements**: 
        - **Authenticated User**: Any logged-in user with verified email can access their own profile
        
        **📋 Use Cases**:
        - Profile page display
        - User settings retrieval
        - Current user context
        - Check email verification status
        
        **✨ Benefits**:
        - No need to know your own user ID
        - Always returns current user's data
        - Safe endpoint for user self-service
        - Shows email verification status
        """,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="✅ Current user profile retrieved",
                examples=[
                    OpenApiExample(
                        'Current User Profile',
                        summary='Your profile information',
                        value={
                            'id': 'current-user-uuid',
                            'email': 'your@email.com',
                            'first_name': 'Your',
                            'last_name': 'Name',
                            'phone': '+1234567890',
                            'status': 'active',
                            'is_email_verified': True
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified")
        },
        tags=["User Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current user's profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @extend_schema(
        summary="✏️ Update current user profile",
        description="""
        Update the profile of the currently authenticated user.
        
        **🔐 Permission Requirements**: 
        - **Authenticated User**: Any logged-in user with verified email can update their own profile
        
        **📝 Updatable Fields**:
        - Personal information (name, phone)
        - Contact details
        - Account preferences
        
        **🚫 Restricted Fields**:
        - Cannot change: `email`, `status`, admin flags, `is_email_verified`
        - Staff-only fields require staff permissions
        - Email changes not allowed for security
        """,
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="✅ Profile updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified")
        },
        tags=["User Management"]
    )
    @action(detail=False, methods=['patch'], permission_classes=[IsAuthenticated])
    def update_me(self, request):
        """Update current user's profile"""
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="🔄 Change user status",
        description="""
        Change the status of a user account (Staff only operation).
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access to status changes
        - **✅ Staff Members**: Can change any user's status
        - **✅ Superusers**: Can change any user's status
        - **⚠️ Email Verification Required**: Staff must have verified email
        
        **📊 Available Status Values**:
        - `active`: Normal active user account
        - `suspended`: Temporarily disabled account  
        - `forever_disabled`: Permanently disabled account
        
        **⚡ Use Cases**:
        - Account suspension for policy violations
        - Account reactivation after review
        - Bulk account management
        
        **🔒 Security Notes**:
        - Status changes are logged
        - Affects user's ability to login
        - Consider impact on active sessions
        - Does not affect email verification status
        """,
        request=UserStatusChangeSerializer,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="✅ User status changed successfully",
                examples=[
                    OpenApiExample(
                        'Status Changed',
                        summary='User account suspended',
                        value={
                            'id': 'user-uuid',
                            'email': 'problem_user@example.com',
                            'status': 'suspended',
                            'updated_at': '2024-01-15T11:00:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="❌ Invalid status value",
                examples=[
                    OpenApiExample(
                        'Invalid Status',
                        summary='Invalid status provided',
                        value={'error': 'Invalid status'}
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Staff access required",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        summary='Regular user attempted status change',
                        value={'error': 'Only staff can change user status'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 User not found")
        },
        tags=["User Management"]
    )
    @action(detail=True, methods=['patch'], permission_classes=[UserPermission])
    def change_status(self, request, pk=None):
        """Change user status (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can change user status'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        user = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(User._meta.get_field('status').choices):
            return Response(
                {'error': 'Invalid status'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.status = new_status
        user.save()
        
        return Response(UserSerializer(user).data)
    
    @extend_schema(
        summary="➕ Create privileged user (Admin only)",
        description="""
        Create a user with elevated privileges (Staff/Superuser only).
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access
        - **❌ Staff Members**: No access  
        - **✅ Superuser ONLY**: Can create staff/superuser accounts
        - **⚠️ Email Verification Required**: Superuser must have verified email
        
        **⚠️ SECURITY WARNING**:
        - This endpoint allows creating staff and superuser accounts
        - Use with extreme caution
        - Consider using Django Admin instead
        - Created users still need to verify their email unless explicitly set
        """,
        request=AdminUserCreateSerializer,
        responses={
            201: OpenApiResponse(response=UserSerializer, description="✅ Privileged user created"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Superuser access required")
        },
        tags=["User Management"]
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def create_privileged(self, request):
        """Create a user with elevated privileges (superuser only)"""
        if not request.user.is_superuser:
            return Response(
                {'error': 'Only superusers can create privileged accounts'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = AdminUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(
        summary="🚫 List blacklist entries",
        description="""
        Retrieve all blacklisted users and their restrictions.
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access to blacklist data
        - **✅ Staff Members**: Can view all blacklist entries
        - **✅ Superusers**: Full access to blacklist data
        - **⚠️ Email Verification Required**: Staff must have verified email
        
        **🛡️ Security Feature**:
        - High-security operation for user safety
        - Contains sensitive restriction information
        - Used for automated access control
        
        **📊 Response Data**:
        - Blacklisted user information (email-based)
        - Restriction reasons and types
        - Blacklist creation and update dates
        """,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer(many=True), description="✅ Blacklist entries retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Staff access required for blacklist",
                examples=[
                    OpenApiExample(
                        'Access Denied',
                        summary='Regular user attempted blacklist access',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            )
        },
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="➕ Add user to blacklist",
        description="""
        Add a user to the blacklist with specified restrictions.
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access to blacklist operations
        - **✅ Staff Members**: Can create blacklist entries
        - **✅ Superusers**: Can create blacklist entries
        - **⚠️ Email Verification Required**: Staff must have verified email
        
        **📝 Required Information**:
        - `user`: User ID to blacklist
        - `reason`: Detailed reason for blacklisting
        - `status`: Type of restriction (temporary/forever/suspended)
        
        **⚠️ High-Impact Operation**:
        - Affects user's system access
        - Should include detailed justification
        - Consider escalation policies
        """,
        request=BlacklistCreateSerializer,
        responses={
            201: OpenApiResponse(response=BlacklistSerializer, description="✅ User added to blacklist"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required")
        },
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get blacklist entry details",
        description="""
        Retrieve detailed information about a specific blacklist entry.
        
        **🔐 Permission Requirements**: Staff access required with verified email
        """,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer, description="✅ Blacklist entry details retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Blacklist entry not found")
        },
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="✏️ Update blacklist entry",
        description="""
        Update blacklist entry details (Staff only).
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access
        - **✅ Staff/Superuser**: Can modify blacklist entries
        - **⚠️ Email Verification Required**: Staff must have verified email
        """,
        request=BlacklistSerializer,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer, description="✅ Blacklist entry updated"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Blacklist entry not found")
        },
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update blacklist entry",
        description="""
        Update specific fields of a blacklist entry (Staff only).
        
        **🔐 Permission Requirements**: Staff access required with verified email
        """,
        request=BlacklistSerializer,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer, description="✅ Blacklist entry updated"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Blacklist entry not found")
        },
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Remove from blacklist",
        description="""
        Remove a user from the blacklist (Staff only).
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access
        - **✅ Staff/Superuser**: Can remove blacklist entries
        - **⚠️ Email Verification Required**: Staff must have verified email
        
        **📋 Use Cases**:
        - User appeal approved
        - Temporary restriction expired
        - Policy change or error correction
        """,
        responses={
            204: OpenApiResponse(description="✅ User removed from blacklist"),
            401: OpenApiResponse(description="🚫 Authentication required or email not verified"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Blacklist entry not found")
        },
        tags=["User Management"]
    ),
)
class BlacklistViewSet(viewsets.ModelViewSet):
    """
    🚫 **Blacklist Management ViewSet - High Security Operations**
    
    Manages user blacklist entries with strict staff-only access:
    - **🔒 Staff Only**: All blacklist operations require staff privileges
    - **📧 Email Verification Required**: Staff must have verified email
    - **📊 Security Logging**: All operations should be logged
    - **⚡ Access Control**: Affects user system access immediately
    """
    queryset = Blacklist.objects.all()
    permission_classes = [BlacklistPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BlacklistFilter
    search_fields = ['reason', 'user__email', 'user__first_name', 'user__last_name']
    ordering_fields = ['created_at', 'updated_at', 'status']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return BlacklistCreateSerializer
        return BlacklistSerializer 