from rest_framework import permissions


class AgentPermission(permissions.BasePermission):
    """
    Custom permission for Agent operations
    - Users can view agents in their workspaces
    - Staff can view all agents
    - Only staff can create/modify agents
    - Only superusers can delete agents
    """
    
    def has_permission(self, request, view):
        # Authenticated users can access the API for read operations
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write operations (create/update) require staff privileges
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff)
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view agents in their workspaces, staff can view all
            return (request.user in obj.workspace.users.all() or 
                   request.user.is_staff)
        
        # Write permissions only for staff
        if request.method in ['PUT', 'PATCH']:
            return request.user.is_staff
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
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