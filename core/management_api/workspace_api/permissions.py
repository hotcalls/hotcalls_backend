from rest_framework import permissions


class WorkspacePermission(permissions.BasePermission):
    """
    Custom permission for Workspace operations
    - Users can view workspaces they belong to
    - Users can modify workspaces they belong to
    - Users can create their first workspace
    - Staff can view and modify all workspaces
    - Only superusers can delete workspaces
    """
    
    def has_permission(self, request, view):
        # All operations require authentication
        if not (request.user and request.user.is_authenticated):
            return False
            
        # Read operations: authenticated users can access
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Update operations: authenticated users can modify (workspace validation in has_object_permission)
        if request.method in ['PUT', 'PATCH']:
            return True
            
        # Create operations: allow users to create their first workspace or staff to create any
        if request.method == 'POST':
            # Staff can always create workspaces
            if request.user.is_staff:
                return True
            
            # Regular users can create workspace if they don't have any
            from core.models import Workspace
            user_workspaces_count = Workspace.objects.filter(users=request.user).count()
            return user_workspaces_count == 0
        
        # Delete operations: require superuser privileges  
        if request.method == 'DELETE':
            return request.user.is_superuser
            
        return False
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view workspaces they belong to, staff can view all
            return (request.user in obj.users.all() or 
                   request.user.is_staff)
        
        # Update permissions: users can modify workspaces they belong to, staff can modify all
        if request.method in ['PUT', 'PATCH']:
            return (request.user in obj.users.all() or 
                   request.user.is_staff)
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
        return False


class WorkspaceUserManagementPermission(permissions.BasePermission):
    """
    Permission for managing users in workspaces
    - Staff can always manage
    - Workspace admin can manage users of their own workspace
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Staff allowed
        if request.user.is_staff:
            return True
        # Workspace admin allowed on their workspace
        from core.models import Workspace
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, 'workspace', None)
        return bool(workspace and workspace.admin_user_id and workspace.admin_user_id == request.user.id)


class IsWorkspaceMemberOrStaff(permissions.BasePermission):
    """
    Permission to only allow workspace members or staff to access workspace resources
    """
    
    def has_object_permission(self, request, view, obj):
        # Check if user is a member of the workspace or is staff
        return (request.user in obj.users.all() or 
                request.user.is_staff)


class WorkspaceInvitationPermission(permissions.BasePermission):
    """
    Permission for workspace invitation operations
    - Only workspace members can send invitations
    - Only workspace members can view workspace invitations
    - Staff can manage all invitations
    """
    
    def has_permission(self, request, view):
        # All operations require authentication
        if not (request.user and request.user.is_authenticated):
            return False
        return True
    
    def has_object_permission(self, request, view, obj):
        # For workspace-related operations, check workspace membership
        if hasattr(obj, 'workspace'):
            workspace = obj.workspace
        else:
            workspace = obj  # obj is the workspace itself
        
        # Staff can manage all invitations
        if request.user.is_staff:
            return True
        
        # Users can only manage invitations for workspaces they belong to
        return request.user in workspace.users.all()


class InvitationAcceptancePermission(permissions.BasePermission):
    """
    Permission for accepting invitations
    - User must be authenticated
    - User's email must match the invitation email
    """
    
    def has_permission(self, request, view):
        # Must be authenticated to accept invitations
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # User's email must match the invitation email
        return request.user.email == obj.email


class PublicInvitationViewPermission(permissions.BasePermission):
    """
    Permission for viewing invitation details (public endpoint)
    - Anyone can view invitation details (no authentication required)
    """
    
    def has_permission(self, request, view):
        return True  # Public access
    
    def has_object_permission(self, request, view, obj):
        return True  # Public access to invitation details


class IsWorkspaceAdmin(permissions.BasePermission):
    """Allow only workspace admin (or staff) for certain actions."""
    def has_object_permission(self, request, view, obj):
        from core.models import Workspace
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, 'workspace', None)
        if workspace is None:
            return False
        if request.user.is_staff:
            return True
        return bool(workspace.admin_user_id and workspace.admin_user_id == request.user.id) 