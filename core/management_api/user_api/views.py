from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import User, Blacklist
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    UserStatusChangeSerializer, BlacklistSerializer, BlacklistCreateSerializer
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
        
        **📊 Response Filtering**:
        - Regular users receive only 1 result (themselves)
        - Staff/Superusers receive all users with pagination
        
        **🎯 Use Cases**:
        - User profile management
        - Staff user administration
        - System user overview
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
                                'username': 'current_user',
                                'first_name': 'John',
                                'last_name': 'Doe',
                                'email': 'john@example.com',
                                'status': 'active'
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
                                {'id': 'uuid1', 'username': 'user1', 'status': 'active'},
                                {'id': 'uuid2', 'username': 'user2', 'status': 'suspended'}
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access user data"),
            403: OpenApiResponse(description="🚫 Permission denied - Authentication required for user access")
        },
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="➕ Create new user",
        description="""
        Create a new user account - **Public endpoint, no authentication required**.
        
        **🔐 Permission Requirements**: 
        - **Public Access**: Anyone can create a new user account (registration)
        - No authentication needed for account creation
        
        **📝 Required Fields**:
        - `username`: Unique username (required)
        - `email`: Valid email address (required)  
        - `password`: Secure password min 8 characters (required)
        - `first_name`, `last_name`: User's name (required)
        - `phone`: Contact phone number (required)
        
        **⚙️ Optional Fields**:
        - `social_id`, `social_provider`: For social media login integration
        
        **🔒 Security Notes**:
        - Password is automatically hashed
        - New users created with `is_staff=False`, `is_superuser=False`
        - Account created with `status=active` by default
        """,
        request=UserCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=UserSerializer,
                description="✅ User account created successfully",
                examples=[
                    OpenApiExample(
                        'Successful Registration',
                        summary='New user account created',
                        description='User successfully registered and account is active',
                        value={
                            'id': 'new-user-uuid',
                            'username': 'new_user123',
                            'first_name': 'Jane',
                            'last_name': 'Smith',
                            'email': 'jane@example.com',
                            'phone': '+1234567890',
                            'status': 'active',
                            'is_active': True,
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
                            'username': ['This field is required.'],
                            'password': ['Ensure this field has at least 8 characters.'],
                            'email': ['Enter a valid email address.']
                        }
                    )
                ]
            )
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
        
        **🛡️ Access Control**:
        - Users attempting to access other profiles get 404 (not 403 for security)
        - Staff can see all user details including sensitive information
        - Response includes role-based field filtering
        """,
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="✅ User details retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
        
        **🔄 Update Scope**:
        - Replaces all editable fields with new values
        - Cannot modify: `id`, `date_joined`, `last_login`
        - Staff can modify: `status`, admin flags
        - Users can modify: personal information only
        """,
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="✅ User updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
        
        **🎯 Partial Update Benefits**:
        - Only send fields you want to change
        - Other fields remain unchanged
        - More efficient for single field updates
        """,
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="✅ User updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
            401: OpenApiResponse(description="🚫 Authentication required"),
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
    🔐 **User Management ViewSet with Role-Based Access Control**
    
    Provides comprehensive user management with different access levels:
    - **👤 Regular Users**: Self-management only
    - **👔 Staff**: Full user administration  
    - **🔧 Superusers**: Complete system control
    """
    queryset = User.objects.all()
    permission_classes = [UserPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = UserFilter
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['username', 'email', 'date_joined', 'last_login']
    ordering = ['-date_joined']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
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
        - **Authenticated User**: Any logged-in user can access their own profile
        
        **📋 Use Cases**:
        - Profile page display
        - User settings retrieval
        - Current user context
        
        **✨ Benefits**:
        - No need to know your own user ID
        - Always returns current user's data
        - Safe endpoint for user self-service
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
                            'username': 'your_username',
                            'first_name': 'Your',
                            'last_name': 'Name',
                            'email': 'your@email.com',
                            'status': 'active'
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login first")
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
        - **Authenticated User**: Any logged-in user can update their own profile
        
        **📝 Updatable Fields**:
        - Personal information (name, email, phone)
        - Account preferences
        - Contact details
        
        **🚫 Restricted Fields**:
        - Cannot change: username, status, admin flags
        - Staff-only fields require staff permissions
        """,
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(response=UserSerializer, description="✅ Profile updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required")
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
                            'username': 'problem_user',
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
            401: OpenApiResponse(description="🚫 Authentication required"),
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


@extend_schema_view(
    list=extend_schema(
        summary="🚫 List blacklist entries",
        description="""
        Retrieve all blacklisted users and their restrictions.
        
        **🔐 Permission Requirements**: 
        - **❌ Regular Users**: No access to blacklist data
        - **✅ Staff Members**: Can view all blacklist entries
        - **✅ Superusers**: Full access to blacklist data
        
        **🛡️ Security Feature**:
        - High-security operation for user safety
        - Contains sensitive restriction information
        - Used for automated access control
        
        **📊 Response Data**:
        - Blacklisted user information
        - Restriction reasons and types
        - Blacklist creation and update dates
        """,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer(many=True), description="✅ Blacklist entries retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required")
        },
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get blacklist entry details",
        description="""
        Retrieve detailed information about a specific blacklist entry.
        
        **🔐 Permission Requirements**: Staff access required
        """,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer, description="✅ Blacklist entry details retrieved"),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
        """,
        request=BlacklistSerializer,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer, description="✅ Blacklist entry updated"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Blacklist entry not found")
        },
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update blacklist entry",
        description="""
        Update specific fields of a blacklist entry (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=BlacklistSerializer,
        responses={
            200: OpenApiResponse(response=BlacklistSerializer, description="✅ Blacklist entry updated"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
        
        **📋 Use Cases**:
        - User appeal approved
        - Temporary restriction expired
        - Policy change or error correction
        """,
        responses={
            204: OpenApiResponse(description="✅ User removed from blacklist"),
            401: OpenApiResponse(description="🚫 Authentication required"),
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
    - **📊 Security Logging**: All operations should be logged
    - **⚡ Access Control**: Affects user system access immediately
    """
    queryset = Blacklist.objects.all()
    permission_classes = [BlacklistPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BlacklistFilter
    search_fields = ['reason', 'user__username', 'user__email']
    ordering_fields = ['created_at', 'updated_at', 'status']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return BlacklistCreateSerializer
        return BlacklistSerializer 