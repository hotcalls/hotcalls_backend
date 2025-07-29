from rest_framework import permissions


class WorkspacePermission(permissions.BasePermission):
    """
    Custom permission for Workspace operations
    - Users can view workspaces they belong to
    - Users can modify workspaces they belong to
    - Staff can view and modify all workspaces
    - Only staff can create new workspaces
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
            
        # Create operations: require staff privileges
        if request.method == 'POST':
            return request.user.is_staff
        
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