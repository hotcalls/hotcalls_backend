from rest_framework import permissions


class WorkspacePermission(permissions.BasePermission):
    """
    Custom permission for Workspace operations
    - Users can view workspaces they belong to
    - Users can modify workspaces they belong to
    - Users can create their first workspace
    - Staff can view and modify all workspaces
    - Staff can create unlimited workspaces
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
    - Only staff can add/remove users from workspaces
    """
    
    def has_permission(self, request, view):
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff)


class IsWorkspaceMemberOrStaff(permissions.BasePermission):
    """
    Permission to only allow workspace members or staff to access workspace resources
    """
    
    def has_object_permission(self, request, view, obj):
        # Check if user is a member of the workspace or is staff
        return (request.user in obj.users.all() or 
                request.user.is_staff) 