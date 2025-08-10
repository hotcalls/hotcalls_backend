from django.db.models import Q, Count, Avg, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from core.models import Workspace, User, WorkspaceInvitation
from core.utils import send_workspace_invitation_email
from .serializers import (
    WorkspaceSerializer, 
    WorkspaceCreateSerializer,
    WorkspaceUserSerializer,
    WorkspaceUserAssignmentSerializer,
    WorkspaceStatsSerializer,
    WorkspaceInvitationSerializer,
    WorkspaceInviteUserSerializer,
    WorkspaceInviteBulkSerializer,
    InvitationDetailSerializer
)
from .permissions import (
    WorkspacePermission, 
    WorkspaceUserManagementPermission, 
    IsWorkspaceMemberOrStaff,
    WorkspaceInvitationPermission,
    InvitationAcceptancePermission,
    PublicInvitationViewPermission
)
from .filters import WorkspaceFilter


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
        Update workspace information.
        
        **🔐 Permission Requirements**:
        - **✅ Regular Users**: Can update workspaces they belong to
        - **✅ Staff Members**: Can update any workspace details
        - **✅ Superusers**: Can update any workspace details
        
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
            403: OpenApiResponse(
                description="🚫 Permission denied - You can only update workspaces you belong to",
                examples=[
                    OpenApiExample(
                        'Not a workspace member',
                        summary='User attempted to update workspace they don\'t belong to',
                        value={'detail': 'You do not have permission to perform this action.'}
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Management"]
    ),
    partial_update=extend_schema(
        summary="✏️ Partially update workspace",
        description="""
        Update specific fields of a workspace.
        
        **🔐 Permission Requirements**:
        - **✅ Regular Users**: Can update workspaces they belong to
        - **✅ Staff Members**: Can update any workspace details
        - **✅ Superusers**: Can update any workspace details
        """,
        request=WorkspaceCreateSerializer,
        responses={
            200: OpenApiResponse(response=WorkspaceSerializer, description="✅ Workspace updated successfully"),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(
                description="🚫 Permission denied - You can only update workspaces you belong to"
            ),
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
    - **👤 Regular Users**: Can view and modify workspaces they belong to
    - **👔 Staff**: Full workspace administration across all workspaces
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
    
    def perform_create(self, serializer):
        """Create workspace and automatically add creator as member"""
        workspace = serializer.save()
        # Add the creator as a member of the workspace
        workspace.users.add(self.request.user)
        workspace.save()
    
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
        # Return stats data directly - no serializer validation needed for computed data
        return Response(stats)

    @extend_schema(
        summary="🏠 Get my workspaces",
        description="""
        Retrieve all workspaces that the authenticated user belongs to.
        
        **🔐 Permission Requirements**:
        - **✅ Authenticated Users**: Get their own workspace memberships
        - **✅ Staff Members**: Get all workspaces in the system
        - **✅ Superusers**: Get all workspaces in the system
        
        **📊 Response Details**:
        - Only workspaces where user is a member
        - Complete workspace information
        - User count and basic statistics
        
        **🎯 Use Cases**:
        - User workspace selection
        - Dashboard workspace listing
        - Navigation and routing
        - Frontend workspace initialization
        """,
        responses={
            200: OpenApiResponse(
                response=WorkspaceSerializer(many=True),
                description="✅ User workspaces retrieved successfully",
                examples=[
                    OpenApiExample(
                        'My Workspaces',
                        summary='User\'s workspace memberships',
                        value=[
                            {
                                'id': 'workspace-uuid-1',
                                'workspace_name': 'John Doe Workspace',
                                'user_count': 1,
                                'created_at': '2024-01-10T09:00:00Z',
                                'updated_at': '2024-01-10T09:00:00Z'
                            },
                            {
                                'id': 'workspace-uuid-2',
                                'workspace_name': 'Team Project Alpha',
                                'user_count': 3,
                                'created_at': '2024-01-12T14:30:00Z',
                                'updated_at': '2024-01-15T10:20:00Z'
                            }
                        ]
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required - Please login to access workspaces")
        },
        tags=["Workspace Management"]
    )
    @action(detail=False, methods=['get'])
    def my_workspaces(self, request):
        """Get workspaces that the authenticated user belongs to"""
        # Get user's workspaces (same logic as get_queryset but explicit)
        user = request.user
        if user.is_staff:
            workspaces = Workspace.objects.all()
        else:
            workspaces = Workspace.objects.filter(users=user)
        
        serializer = WorkspaceSerializer(workspaces, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="📧 Invite user to workspace",
        description="""
        Send an invitation email to a user to join this workspace.
        
        **🔐 Permission Requirements**:
        - **✅ Workspace Members**: Can invite others to their workspaces
        - **✅ Staff Members**: Can invite users to any workspace
        - **✅ Superusers**: Can invite users to any workspace
        
        **📝 Invitation Process**:
        1. Validates email address and checks for existing memberships
        2. Creates secure invitation token (7-day expiry)
        3. Sends professional invitation email
        4. Returns invitation details for tracking
        
        **✉️ Email Content**:
        - Beautiful HTML template with workspace details
        - Secure invitation link with token
        - Clear instructions for accepting
        - 7-day expiration notice
        
        **🔄 Existing Users vs New Users**:
        - **Existing Users**: Can login and accept immediately
        - **New Users**: Must register first, then accept invitation
        """,
        request=WorkspaceInviteUserSerializer,
        responses={
            201: OpenApiResponse(
                response=WorkspaceInvitationSerializer,
                description="✅ Invitation sent successfully",
                examples=[
                    OpenApiExample(
                        'Invitation Sent',
                        summary='User invitation created and email sent',
                        value={
                            'id': 'invitation-uuid',
                            'email': 'colleague@example.com',
                            'status': 'pending',
                            'workspace_name': 'Sales Team',
                            'invited_by_name': 'John Doe',
                            'invited_by_email': 'john@company.com',
                            'created_at': '2024-01-15T10:30:00Z',
                            'expires_at': '2024-01-22T10:30:00Z',
                            'is_valid': True
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="❌ Validation error - User already member or pending invitation exists",
                examples=[
                    OpenApiExample(
                        'Already Member',
                        summary='User is already a workspace member',
                        value={'email': ['This user is already a member of the workspace']}
                    ),
                    OpenApiExample(
                        'Pending Invitation',
                        summary='Invitation already pending',
                        value={'email': ['A pending invitation already exists for this email address']}
                    )
                ]
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied - Not a workspace member"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Invitations"]
    )
    @action(detail=True, methods=['post'], permission_classes=[WorkspaceInvitationPermission])
    def invite(self, request, pk=None):
        """Send invitation to join workspace"""
        workspace = self.get_object()
        serializer = WorkspaceInviteUserSerializer(
            data=request.data,
            context={'workspace': workspace}
        )
        
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            # Cancel any existing expired invitations for this email/workspace
            WorkspaceInvitation.objects.filter(
                workspace=workspace,
                email=email,
                status='pending'
            ).update(status='cancelled')
            
            # Create new invitation
            invitation = WorkspaceInvitation.objects.create(
                workspace=workspace,
                email=email,
                invited_by=request.user
            )
            
            # Send invitation email
            email_sent = send_workspace_invitation_email(invitation, request)
            
            if email_sent:
                # Return invitation details
                invitation_serializer = WorkspaceInvitationSerializer(invitation)
                return Response(invitation_serializer.data, status=status.HTTP_201_CREATED)
            else:
                # Email failed - cancel invitation
                invitation.cancel()
                return Response(
                    {'error': 'Failed to send invitation email'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="📧📧 Bulk invite users to workspace",
        description="""
        Send invitations to multiple users at once.
        
        **🔐 Permission Requirements**: Workspace members and staff only
        
        **📊 Bulk Processing**:
        - Validates all email addresses before sending
        - Skips users already in workspace or with pending invitations
        - Sends individual invitation emails
        - Returns detailed success/failure report
        
        **⚡ Performance**:
        - Maximum 50 invitations per request
        - Efficient validation and processing
        - Detailed error reporting per email
        """,
        request=WorkspaceInviteBulkSerializer,
        responses={
            200: OpenApiResponse(
                description="✅ Bulk invitations processed",
                examples=[
                    OpenApiExample(
                        'Bulk Invitations',
                        summary='Mixed success/failure results',
                        value={
                            'successful_invitations': [
                                {'email': 'user1@example.com', 'invitation_id': 'uuid1'},
                                {'email': 'user2@example.com', 'invitation_id': 'uuid2'}
                            ],
                            'failed_invitations': [
                                {'email': 'existing@example.com', 'error': 'Already a member'}
                            ],
                            'summary': {
                                'total_processed': 3,
                                'successful': 2,
                                'failed': 1
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="❌ Validation error"),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied")
        },
        tags=["Workspace Invitations"]
    )
    @action(detail=True, methods=['post'], permission_classes=[WorkspaceInvitationPermission])
    def bulk_invite(self, request, pk=None):
        """Send bulk invitations to join workspace"""
        workspace = self.get_object()
        serializer = WorkspaceInviteBulkSerializer(
            data=request.data,
            context={'workspace': workspace}
        )
        
        if serializer.is_valid():
            emails = serializer.validated_data['emails']
            successful_invitations = []
            failed_invitations = []
            
            for email in emails:
                try:
                    # Cancel any existing expired invitations
                    WorkspaceInvitation.objects.filter(
                        workspace=workspace,
                        email=email,
                        status='pending'
                    ).update(status='cancelled')
                    
                    # Create new invitation
                    invitation = WorkspaceInvitation.objects.create(
                        workspace=workspace,
                        email=email,
                        invited_by=request.user
                    )
                    
                    # Send invitation email
                    email_sent = send_workspace_invitation_email(invitation, request)
                    
                    if email_sent:
                        successful_invitations.append({
                            'email': email,
                            'invitation_id': str(invitation.id)
                        })
                    else:
                        invitation.cancel()
                        failed_invitations.append({
                            'email': email,
                            'error': 'Failed to send email'
                        })
                        
                except Exception as e:
                    failed_invitations.append({
                        'email': email,
                        'error': str(e)
                    })
            
            return Response({
                'successful_invitations': successful_invitations,
                'failed_invitations': failed_invitations,
                'summary': {
                    'total_processed': len(emails),
                    'successful': len(successful_invitations),
                    'failed': len(failed_invitations)
                }
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="📋 List workspace invitations",
        description="""
        Retrieve all invitations for this workspace.
        
        **🔐 Permission Requirements**: Workspace members and staff only
        
        **📊 Invitation Information**:
        - Invitation status (pending, accepted, expired, cancelled)
        - Invitee email and expiration date
        - Inviter information
        - Invitation validity status
        
        **🎯 Use Cases**:
        - Monitor pending invitations
        - Track invitation history
        - Manage workspace access
        """,
        responses={
            200: OpenApiResponse(
                response=WorkspaceInvitationSerializer(many=True),
                description="✅ Workspace invitations retrieved successfully"
            ),
            401: OpenApiResponse(description="🚫 Authentication required"),
            403: OpenApiResponse(description="🚫 Permission denied"),
            404: OpenApiResponse(description="🚫 Workspace not found")
        },
        tags=["Workspace Invitations"]
    )
    @action(detail=True, methods=['get'], permission_classes=[WorkspaceInvitationPermission])
    def invitations(self, request, pk=None):
        """List all invitations for this workspace"""
        workspace = self.get_object()
        invitations = workspace.invitations.all().order_by('-created_at')
        serializer = WorkspaceInvitationSerializer(invitations, many=True)
        return Response(serializer.data)


class InvitationDetailView(viewsets.GenericViewSet):
    """
    🎯 **Public Invitation Management**
    
    Handles public invitation operations:
    - **View invitation details** (public, no auth required)
    - **Accept invitations** (authenticated users only)
    """
    queryset = WorkspaceInvitation.objects.all()
    lookup_field = 'token'
    lookup_url_kwarg = 'token'
    
    def get_permissions(self):
        """Different permissions for different actions"""
        if self.action == 'retrieve':
            return [PublicInvitationViewPermission()]
        elif self.action == 'accept':
            return [InvitationAcceptancePermission()]
        return [PublicInvitationViewPermission()]
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'retrieve':
            return InvitationDetailSerializer
        return InvitationDetailSerializer
    
    @extend_schema(
        summary="🔍 Get invitation details",
        description="""
        **🌐 PUBLIC ENDPOINT** - View invitation details using the invitation token.
        
        **🔓 Access**: No authentication required (public endpoint)
        
        **📋 Information Provided**:
        - Workspace name and details
        - Inviter information
        - Invitation expiration status
        - Email address for verification
        
        **🎯 Use Cases**:
        - Display invitation page before login
        - Verify invitation validity
        - Show workspace information to potential members
        
        **🛡️ Security Notes**:
        - Only basic workspace information is exposed
        - No sensitive data in public endpoint
        - Token-based access only
        """,
        responses={
            200: OpenApiResponse(
                response=InvitationDetailSerializer,
                description="✅ Invitation details retrieved successfully",
                examples=[
                    OpenApiExample(
                        'Valid Invitation',
                        summary='Active invitation details',
                        value={
                            'email': 'colleague@example.com',
                            'workspace_name': 'Sales Team',
                            'invited_by_name': 'John Doe',
                            'created_at': '2024-01-15T10:30:00Z',
                            'expires_at': '2024-01-22T10:30:00Z',
                            'is_valid': True
                        }
                    ),
                    OpenApiExample(
                        'Expired Invitation',
                        summary='Expired invitation',
                        value={
                            'email': 'colleague@example.com',
                            'workspace_name': 'Sales Team',
                            'invited_by_name': 'John Doe',
                            'created_at': '2024-01-08T10:30:00Z',
                            'expires_at': '2024-01-15T10:30:00Z',
                            'is_valid': False
                        }
                    )
                ]
            ),
            404: OpenApiResponse(
                description="🚫 Invitation not found or invalid token",
                examples=[
                    OpenApiExample(
                        'Invalid Token',
                        summary='Invitation token not found',
                        value={'detail': 'Not found.'}
                    )
                ]
            )
        },
        tags=["Public Invitations"]
    )
    def retrieve(self, request, token=None):
        """Get invitation details (public endpoint)"""
        try:
            invitation = WorkspaceInvitation.objects.get(token=token)
            serializer = InvitationDetailSerializer(invitation)
            return Response(serializer.data)
        except WorkspaceInvitation.DoesNotExist:
            return Response(
                {'error': 'Invitation not found or invalid token'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @extend_schema(
        summary="✅ Accept workspace invitation",
        description="""
        Accept a workspace invitation and join the workspace.
        
        **🔐 Authentication Required**: User must be logged in to accept invitations
        
        **✉️ Email Verification**: User's email must match the invitation email
        
        **🔄 Acceptance Process**:
        1. Validates invitation token and expiration
        2. Verifies user's email matches invitation email
        3. Adds user to workspace
        4. Updates invitation status to 'accepted'
        5. Returns success confirmation
        
        **⚠️ Security Validations**:
        - User must be authenticated
        - Email addresses must match exactly
        - Invitation must be pending and not expired
        - Token must be valid and secure
        
        **🎯 Different User Scenarios**:
        - **Existing Users**: Login → Accept → Immediate access
        - **New Users**: Register → Verify email → Accept → Access
        """,
        responses={
            200: OpenApiResponse(
                description="✅ Invitation accepted successfully - User added to workspace",
                examples=[
                    OpenApiExample(
                        'Successful Acceptance',
                        summary='User successfully joined workspace',
                        value={
                            'message': 'Successfully joined workspace',
                            'workspace_name': 'Sales Team',
                            'workspace_id': 'workspace-uuid',
                            'user_email': 'colleague@example.com'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="❌ Invalid invitation or validation error",
                examples=[
                    OpenApiExample(
                        'Expired Invitation',
                        summary='Invitation has expired',
                        value={'error': 'Invitation is not valid or has expired'}
                    )
                ]
            ),
            401: OpenApiResponse(
                description="🚫 Authentication required - User must login to accept invitations",
                examples=[
                    OpenApiExample(
                        'Not Authenticated',
                        summary='User needs to login',
                        value={'detail': 'Authentication credentials were not provided.'}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="🚫 Email mismatch - Wrong user account",
                examples=[
                    OpenApiExample(
                        'Email Mismatch',
                        summary='User email doesn\'t match invitation',
                        value={
                            'error': 'This invitation was sent to a different email address',
                            'invited_email': 'colleague@example.com',
                            'your_email': 'different@example.com'
                        }
                    )
                ]
            ),
            404: OpenApiResponse(description="🚫 Invitation not found or invalid token")
        },
        tags=["Public Invitations"]
    )
    @action(detail=False, methods=['post'], url_path='(?P<token>[^/.]+)/accept')
    def accept(self, request, token=None):
        """Accept workspace invitation (authenticated users only)"""
        try:
            invitation = WorkspaceInvitation.objects.get(token=token)
        except WorkspaceInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired invitation'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if invitation is valid
        if not invitation.is_valid():
            return Response(
                {'error': 'Invitation is not valid or has expired'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify email matches
        if request.user.email != invitation.email:
            return Response({
                'error': 'This invitation was sent to a different email address',
                'invited_email': invitation.email,
                'your_email': request.user.email
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # Accept the invitation
            invitation.accept(request.user)
            
            return Response({
                'message': 'Successfully joined workspace',
                'workspace_name': invitation.workspace.workspace_name,
                'workspace_id': str(invitation.workspace.id),
                'user_email': request.user.email
            })
            
        except ValueError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': 'An error occurred while accepting the invitation'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 