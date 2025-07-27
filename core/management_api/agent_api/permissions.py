from rest_framework import permissions


class AgentPermission(permissions.BasePermission):
    """
    Custom permission for Agent operations
    - Users can view agents in their workspaces
    - Users can create, update, and delete agents in workspaces they belong to
    - Staff can view and manage all agents in any workspace
    - Full workspace-based access control
    """
    
    def has_permission(self, request, view):
        # All operations require authentication
        if not (request.user and request.user.is_authenticated):
            return False
            
        # Read operations: authenticated users can access
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Create operations: authenticated users can create (workspace validation in serializer)
        if request.method == 'POST':
            return True
        
        # Update operations: authenticated users can modify (workspace validation in has_object_permission)
        if request.method in ['PUT', 'PATCH']:
            return True
            
        # Delete operations: authenticated users can delete (workspace validation in has_object_permission)
        if request.method == 'DELETE':
            return True
            
        return False
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view agents in their workspaces, staff can view all
            return (request.user in obj.workspace.users.all() or 
                   request.user.is_staff)
        
        # Create operations don't need object permissions (handled by has_permission + serializer validation)
        if request.method == 'POST':
            return True
        
        # Update permissions: users can modify agents in their workspaces, staff can modify all
        if request.method in ['PUT', 'PATCH']:
            return (request.user in obj.workspace.users.all() or 
                   request.user.is_staff)
        
        # Delete permissions: users can delete agents in their workspaces, staff can delete all
        if request.method == 'DELETE':
            return (request.user in obj.workspace.users.all() or 
                   request.user.is_staff)
        
        return False


class PhoneNumberPermission(permissions.BasePermission):
    """
    Custom permission for PhoneNumber operations
    - All authenticated users can view phone numbers
    - Only staff can create/modify phone numbers
    - Only superusers can delete phone numbers
    """
    
    def has_permission(self, request, view):
        # Authenticated users can access the API for read operations
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write operations require staff privileges
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff)
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write permissions for staff
        if request.method in ['PUT', 'PATCH']:
            return request.user.is_staff
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
        return False


class AgentPhoneManagementPermission(permissions.BasePermission):
    """
    Permission for managing phone numbers in agents
    - Only staff can assign/remove phone numbers from agents
    """
    
    def has_permission(self, request, view):
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff) 