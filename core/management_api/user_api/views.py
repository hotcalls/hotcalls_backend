from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.models import User, Blacklist
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    BlacklistSerializer, BlacklistCreateSerializer
)
from .filters import UserFilter, BlacklistFilter
from .permissions import UserPermission, BlacklistPermission


@extend_schema_view(
    list=extend_schema(
        summary="List all users",
        description="Retrieve a list of all users with filtering and search capabilities",
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="Create a new user",
        description="Create a new user account",
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="Get user details",
        description="Retrieve detailed information about a specific user",
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="Update user",
        description="Update all fields of a user",
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update user",
        description="Update specific fields of a user",
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="Delete user",
        description="Delete a user account (superuser only)",
        tags=["User Management"]
    ),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User model operations
    
    Provides CRUD operations for users with proper permissions:
    - Users can view and edit their own profile
    - Staff can view all users
    - Superusers can perform all operations
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
        summary="Get current user profile",
        description="Get the profile of the currently authenticated user",
        tags=["User Management"]
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current user's profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Update current user profile",
        description="Update the profile of the currently authenticated user",
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
        summary="Change user status",
        description="Change the status of a user (staff only)",
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
        summary="List blacklist entries",
        description="Retrieve a list of all blacklisted users (staff only)",
        tags=["User Management"]
    ),
    create=extend_schema(
        summary="Create blacklist entry",
        description="Add a user to the blacklist (superuser only)",
        tags=["User Management"]
    ),
    retrieve=extend_schema(
        summary="Get blacklist details",
        description="Retrieve detailed information about a blacklist entry",
        tags=["User Management"]
    ),
    update=extend_schema(
        summary="Update blacklist entry",
        description="Update a blacklist entry (superuser only)",
        tags=["User Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update blacklist entry",
        description="Update specific fields of a blacklist entry (superuser only)",
        tags=["User Management"]
    ),
    destroy=extend_schema(
        summary="Remove from blacklist",
        description="Remove a user from the blacklist (superuser only)",
        tags=["User Management"]
    ),
)
class BlacklistViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Blacklist model operations
    
    Provides CRUD operations for blacklist entries:
    - Only staff can view blacklist entries
    - Only superusers can create/modify blacklist entries
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