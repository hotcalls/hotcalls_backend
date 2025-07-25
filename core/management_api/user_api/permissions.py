from rest_framework import permissions


class UserPermission(permissions.BasePermission):
    """
    Custom permission for User operations
    - Users can view and edit their own profile
    - Staff can view all users
    - Superusers can perform all operations
    """
    
    def has_permission(self, request, view):
        # Authenticated users can access the API
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            # Users can view their own profile, staff can view all
            return obj == request.user or request.user.is_staff
        
        # Write permissions
        if request.method in ['PUT', 'PATCH']:
            # Users can edit their own profile, staff can edit all
            return obj == request.user or request.user.is_staff
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
        return False


class BlacklistPermission(permissions.BasePermission):
    """
    Custom permission for Blacklist operations
    - Only staff can view blacklist entries
    - Only superusers can create/modify blacklist entries
    """
    
    def has_permission(self, request, view):
        # Only staff and superusers can access blacklist
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff)
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for staff
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_staff
        
        # Write/Delete permissions only for superusers
        return request.user.is_superuser


class IsOwnerOrStaff(permissions.BasePermission):
    """
    Permission to only allow owners of an object or staff to access it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to the owner or staff
        if request.method in permissions.SAFE_METHODS:
            return obj == request.user or request.user.is_staff
        
        # Write permissions are only allowed to the owner or staff
        return obj == request.user or request.user.is_staff 