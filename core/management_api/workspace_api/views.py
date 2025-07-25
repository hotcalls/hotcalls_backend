from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample

from core.models import Workspace, User
from .serializers import (
    WorkspaceSerializer, WorkspaceCreateSerializer, WorkspaceUserSerializer,
    WorkspaceUserAssignmentSerializer, WorkspaceStatsSerializer
)
from .filters import WorkspaceFilter
from .permissions import WorkspacePermission, WorkspaceUserManagementPermission


@extend_schema_view(
    list=extend_schema(
        summary="🏢 List workspaces",
        description="""
        Retrieve workspaces based on your access level and membership.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only see workspaces they belong to (filtered)
        - **Staff Members**: Can view all workspaces in the system
        - **Superusers**: Full access to all workspace data
        
        **📊 Response Filtering**:
        - Regular users see only their workspace memberships
        - Staff/Superusers see all workspaces with full details
        
        **🎯 Use Cases**:
        - Workspace selection interface
        - Organization overview
        - Member access control
        """,
        responses={
            200: OpenApiResponse(
                response=WorkspaceSerializer(many=True),
                description="✅ Successfully retrieved workspaces based on access level",
                examples=[
                    OpenApiExample(
                        'Regular User Response',
                        summary='User sees only their workspaces',
                        description='Regular users are filtered to see only workspaces they belong to',
                        value={
                            'count': 2,
                            'results': [
                                {
                                    'id': 'workspace-uuid-1',
                                    'workspace_name': 'My Team Workspace',
                                    'user_count': 5,
                                    'created_at': '2024-01-10T09:00:00Z'
                                },
                                {
                                    'id': 'workspace-uuid-2',
                                    'workspace_name': 'Project Alpha',
                                    'user_count': 3,
                                    'created_at': '2024-01-12T14:30:00Z'
                                }
                            ]
                        }
                    ),
                    OpenApiExample(
                        'Staff User Response',
                        summary='Staff sees all workspaces',
                        description='Staff members can view all workspaces in the system',
                        value={
                            'count': 25,
                            'results': [
                                {'id': 'uuid1', 'workspace_name': 'Sales Team', 'user_count': 8},
                                {'id': 'uuid2', 'workspace_name': 'Marketing', 'user_count': 12}
                            ]
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access workspaces")
        },
        tags=["Workspace Management"]
    ),
    create=extend_schema(
        summary="➕ Create new workspace",
        description="""
        Create a new workspace for organizing users and resources.
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot create workspaces
        - **✅ Staff Members**: Can create new workspaces
        - **✅ Superusers**: Can create new workspaces
        
        **💼 Organization Structure**:
        - Workspaces contain users, agents, and resources
        - Establishes organizational boundaries
        - Controls resource access and permissions
        
        **📝 Required Information**:
        - `workspace_name`: Unique workspace identifier
        - Users can be added separately via user management endpoints
        """,
        request=WorkspaceCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=WorkspaceSerializer,
                description="✅ Workspace created successfully",
                examples=[
                    OpenApiExample(
                        'New Workspace Created',
                        summary='Successfully created workspace',
                        value={
                            'id': 'new-workspace-uuid',
                            'workspace_name': 'Customer Support Team',
                            'user_count': 0,
                            'created_at': '2024-01-15T10:30:00Z'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Workspace name may already exist"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Staff access required for workspace creation",
                examples=[
                    OpenApiExample(
                        'Access Denied',
                        summary='Regular user attempted workspace creation',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            )
        },
        tags=["Workspace Management"]
    ),
    retrieve=extend_schema(
        summary="🔍 Get workspace details",
        description="""
        Retrieve detailed information about a specific workspace.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can only access workspaces they belong to
        - **Staff Members**: Can access any workspace details
        - **Superusers**: Full access to any workspace
        
        **🛡️ Access Control**:
        - Users get 404 for workspaces they don't belong to (security)
        - Staff can see all workspace configuration details
        - Includes user count and membership information
        """,
        responses={
            200: OpenApiResponse(response=WorkspaceSerializer, description="✅ Workspace details retrieved successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Not a workspace member"),
            404: OpenApiResponse(description="🚫 Workspace not found or access denied")
        },
        tags=["Workspace Management"]
    ),
    update=extend_schema(
        summary="✏️ Update workspace",
        description="""
        Update workspace information (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot modify workspaces
        - **✅ Staff Members**: Can update workspace details
        - **✅ Superusers**: Can update workspace details
        
        **⚠️ Organizational Impact**:
        - May affect all workspace members
        - Consider communication for major changes
        - Affects resource organization and access
        """,
        request=WorkspaceCreateSerializer,
        responses={
            200: OpenApiResponse(response=WorkspaceSerializer, description="✅ Workspace updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update workspace",
        description="""
        Update specific fields of a workspace (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        """,
        request=WorkspaceCreateSerializer,
        responses={
            200: OpenApiResponse(response=WorkspaceSerializer, description="✅ Workspace updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    ),
    destroy=extend_schema(
        summary="🗑️ Delete workspace",
        description="""
        **⚠️ DESTRUCTIVE OPERATION - Permanently delete a workspace.**
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: No access to workspace deletion
        - **❌ Staff Members**: Cannot delete workspaces
        - **✅ Superuser ONLY**: Can delete workspaces
        
        **💥 Critical Impact**:
        - Removes all workspace data and relationships
        - Affects all workspace members and agents
        - Cannot be undone - ensure data backup
        
        **🛡️ Safety Considerations**:
        - Ensure all agents and resources are reassigned
        - Communicate with affected users
        - Consider workspace archival instead
        """,
        responses={
            204: OpenApiResponse(description="✅ Workspace deleted successfully"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - Only superusers can delete workspaces",
                examples=[
                    OpenApiExample(
                        'Insufficient Permissions',
                        summary='Non-superuser attempted workspace deletion',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    ),
)
class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    🏢 **Workspace Management with Role-Based Access Control**
    
    Manages organizational workspaces with filtered access:
    - **👤 Regular Users**: Access only their workspace memberships
    - **👔 Staff**: Full workspace administration
    - **🔧 Superusers**: Complete workspace control including deletion
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
        return WorkspaceSerializer
    
    def get_queryset(self):
        """Filter queryset based on user permissions"""
        user = self.request.user
        if user.is_staff:
            return Workspace.objects.all()
        else:
            # Regular users can only see workspaces they belong to
            return Workspace.objects.filter(users=user)
    
    @extend_schema(
        summary="👥 Get workspace users",
        description="""
        Retrieve all users who are members of a specific workspace.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can view users in workspaces they belong to
        - **Staff Members**: Can view users in any workspace
        - **Superusers**: Full access to workspace membership data
        
        **📊 User Information**:
        - Basic user profile information
        - Workspace membership details
        - User role and status in workspace context
        
        **🎯 Use Cases**:
        - Team member listings
        - Workspace directory
        - Access control verification
        """,
        responses={
            200: OpenApiResponse(
                response=WorkspaceUserSerializer(many=True),
                description="✅ Workspace users retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Not a workspace member"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """Get all users in a workspace"""
        workspace = self.get_object()
        users = workspace.users.all()
        serializer = WorkspaceUserSerializer(users, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="➕ Add users to workspace",
        description="""
        Add one or multiple users to a workspace (Staff only).
        
        **🔐 Permission Requirements**:
        - **❌ Regular Users**: Cannot manage workspace membership
        - **✅ Staff Members**: Can add users to any workspace
        - **✅ Superusers**: Can add users to any workspace
        
        **📝 Required Information**:
        - `user_ids`: Array of user IDs to add to the workspace
        
        **💡 Membership Management**:
        - Establishes user-workspace relationships
        - Grants workspace resource access
        - Affects user's workspace filtering
        
        **🔄 Bulk Operation**:
        - Can add multiple users in single request
        - Validates all user IDs before processing
        - Returns success/failure status for each user
        """,
        request=WorkspaceUserAssignmentSerializer,
        responses={
            200: OpenApiResponse(
                description="✅ Users added to workspace successfully",
                examples=[
                    OpenApiExample(
                        'Users Added',
                        summary='Multiple users added to workspace',
                        value={
                            'message': 'Users added successfully',
                            'added_users': ['user-uuid-1', 'user-uuid-2'],
                            'failed_users': [],
                            'total_added': 2
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error - Invalid user IDs"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['post'], permission_classes=[WorkspaceUserManagementPermission])
    def add_users(self, request, pk=None):
        """Add users to a workspace (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can manage workspace users'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        workspace = self.get_object()
        serializer = WorkspaceUserAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            user_ids = serializer.validated_data['user_ids']
            users = User.objects.filter(id__in=user_ids)
            workspace.users.add(*users)
            
            return Response({
                'message': 'Users added successfully',
                'added_users': [str(user.id) for user in users],
                'total_added': len(users)
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="➖ Remove users from workspace",
        description="""
        Remove one or multiple users from a workspace (Staff only).
        
        **🔐 Permission Requirements**: Staff access required
        
        **📝 Required Information**:
        - `user_ids`: Array of user IDs to remove from workspace
        
        **⚠️ Impact**:
        - Removes workspace resource access
        - Affects user's workspace filtering
        - May impact ongoing work and data access
        
        **🔄 Bulk Operation**:
        - Can remove multiple users in single request
        - Validates user membership before removal
        """,
        request=WorkspaceUserAssignmentSerializer,
        responses={
            200: OpenApiResponse(
                description="✅ Users removed from workspace successfully",
                examples=[
                    OpenApiExample(
                        'Users Removed',
                        summary='Users removed from workspace',
                        value={
                            'message': 'Users removed successfully',
                            'removed_users': ['user-uuid-1'],
                            'not_found_users': ['user-uuid-2'],
                            'total_removed': 1
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Staff access required"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['delete'], permission_classes=[WorkspaceUserManagementPermission])
    def remove_users(self, request, pk=None):
        """Remove users from a workspace (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can manage workspace users'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        workspace = self.get_object()
        serializer = WorkspaceUserAssignmentSerializer(data=request.data)
        
        if serializer.is_valid():
            user_ids = serializer.validated_data['user_ids']
            users = User.objects.filter(id__in=user_ids)
            workspace.users.remove(*users)
            
            return Response({
                'message': 'Users removed successfully',
                'removed_users': [str(user.id) for user in users],
                'total_removed': len(users)
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="📊 Get workspace statistics",
        description="""
        Retrieve comprehensive statistics for a workspace.
        
        **🔐 Permission Requirements**:
        - **Regular Users**: Can view stats for workspaces they belong to
        - **Staff Members**: Can view stats for any workspace
        - **Superusers**: Full access to all workspace analytics
        
        **📈 Statistics Included**:
        - User count and membership details
        - Agent count and configuration
        - Resource utilization metrics
        - Activity and usage analytics
        
        **🎯 Business Intelligence**:
        - Workspace performance metrics
        - Resource allocation insights
        - Team productivity indicators
        """,
        responses={
            200: OpenApiResponse(
                response=WorkspaceStatsSerializer,
                description="✅ Workspace statistics retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Workspace Statistics',
                        summary='Complete workspace analytics',
                        value={
                            'workspace_id': 'workspace-uuid',
                            'workspace_name': 'Sales Team',
                            'user_count': 8,
                            'agent_count': 3,
                            'total_calls': 1250,
                            'active_leads': 45,
                            'last_activity': '2024-01-15T09:30:00Z'
                        }
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Not a workspace member"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    )
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get workspace statistics"""
        workspace = self.get_object()
        stats = {
            'workspace_id': str(workspace.id),
            'workspace_name': workspace.workspace_name,
            'user_count': workspace.users.count(),
            'agent_count': workspace.mapping_workspace_agents.count(),
            'calendar_count': workspace.mapping_workspace_calendars.count(),
            'created_at': workspace.created_at,
            'updated_at': workspace.updated_at,
        }
        serializer = WorkspaceStatsSerializer(data=stats)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data) 