from rest_framework import permissions


class WorkspacePermission(permissions.BasePermission):
    """
    Custom permission for Workspace operations
    - Users can view workspaces they belong to
    - Staff can view all workspaces
    - Only staff can create/modify workspaces
    - Only superusers can delete workspaces
    """
    
    def has_permission(self, request, view):
        # Authenticated users can access the API
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view workspaces they belong to, staff can view all
            return (request.user in obj.mapping_user_workspaces.all() or 
                   request.user.is_staff)
        
        # Write permissions only for staff
        if request.method in ['PUT', 'PATCH']:
            return request.user.is_staff
        
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
        return (request.user in obj.mapping_user_workspaces.all() or 
                request.user.is_staff) 