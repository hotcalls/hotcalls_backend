from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.models import Workspace, User
from .serializers import (
    WorkspaceSerializer, WorkspaceCreateSerializer, WorkspaceUpdateSerializer,
    WorkspaceUserAssignmentSerializer, WorkspaceUserSerializer
)
from .filters import WorkspaceFilter
from .permissions import WorkspacePermission, WorkspaceUserManagementPermission


@extend_schema_view(
    list=extend_schema(
        summary="List workspaces",
        description="Retrieve a list of workspaces (users see only their workspaces, staff see all)",
        tags=["Workspace Management"]
    ),
    create=extend_schema(
        summary="Create a new workspace",
        description="Create a new workspace (staff only)",
        tags=["Workspace Management"]
    ),
    retrieve=extend_schema(
        summary="Get workspace details",
        description="Retrieve detailed information about a specific workspace",
        tags=["Workspace Management"]
    ),
    update=extend_schema(
        summary="Update workspace",
        description="Update all fields of a workspace (staff only)",
        tags=["Workspace Management"]
    ),
    partial_update=extend_schema(
        summary="Partially update workspace",
        description="Update specific fields of a workspace (staff only)",
        tags=["Workspace Management"]
    ),
    destroy=extend_schema(
        summary="Delete workspace",
        description="Delete a workspace (superuser only)",
        tags=["Workspace Management"]
    ),
)
class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Workspace model operations
    
    Provides CRUD operations for workspaces:
    - Users can view workspaces they belong to
    - Staff can view all workspaces and create/modify them
    - Superusers can delete workspaces
    """
    queryset = Workspace.objects.all()
    permission_classes = [WorkspacePermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = WorkspaceFilter
    search_fields = ['workspace_name']
    ordering_fields = ['workspace_name', 'created_at', 'updated_at']
    ordering = ['workspace_name']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return WorkspaceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return WorkspaceUpdateSerializer
        return WorkspaceSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return Workspace.objects.all()
        else:
            # Regular users can only see workspaces they belong to
            return Workspace.objects.filter(mapping_user_workspaces=user)
    
    def perform_create(self, serializer):
        """Only staff can create workspaces"""
        if not self.request.user.is_staff:
            raise PermissionError("Only staff can create workspaces")
        serializer.save()
    
    @extend_schema(
        summary="Get workspace users",
        description="Get all users in a specific workspace",
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """Get all users in a specific workspace"""
        workspace = self.get_object()
        users = workspace.mapping_user_workspaces.all()
        serializer = WorkspaceUserSerializer(users, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Add users to workspace",
        description="Add one or more users to a workspace (staff only)",
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[WorkspaceUserManagementPermission])
    def add_users(self, request, pk=None):
        """Add users to a workspace"""
        workspace = self.get_object()
        serializer = WorkspaceUserAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            user_ids = serializer.validated_data['user_ids']
            users = User.objects.filter(id__in=user_ids)
            
            # Add users to workspace
            workspace.mapping_user_workspaces.add(*users)
            
            return Response({
                'message': f'Successfully added {len(users)} users to workspace',
                'added_users': [user.username for user in users]
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Remove users from workspace",
        description="Remove one or more users from a workspace (staff only)",
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[WorkspaceUserManagementPermission])
    def remove_users(self, request, pk=None):
        """Remove users from a workspace"""
        workspace = self.get_object()
        serializer = WorkspaceUserAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            user_ids = serializer.validated_data['user_ids']
            users = User.objects.filter(id__in=user_ids)
            
            # Remove users from workspace
            workspace.mapping_user_workspaces.remove(*users)
            
            return Response({
                'message': f'Successfully removed {len(users)} users from workspace',
                'removed_users': [user.username for user in users]
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Get workspace statistics",
        description="Get statistics about a workspace (user count, etc.)",
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get workspace statistics"""
        workspace = self.get_object()
        
        stats = {
            'user_count': workspace.mapping_user_workspaces.count(),
            'agent_count': workspace.mapping_workspace_agents.count(),
            'calendar_count': workspace.mapping_workspace_calendars.count(),
            'created_at': workspace.created_at,
            'updated_at': workspace.updated_at,
        }
        
        return Response(stats) 