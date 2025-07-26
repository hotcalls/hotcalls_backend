from rest_framework import permissions


class SubscriptionPermission(permissions.BasePermission):
    """
    Custom permission for subscription operations
    - Authenticated users can view plans and features
    - Only staff can create/modify plans and features
    - Only superusers can delete plans and features
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


class PlanFeaturePermission(permissions.BasePermission):
    """
    Custom permission for plan-feature assignments
    - Authenticated users can view plan-feature assignments
    - Only staff can create/modify assignments
    - Only staff can delete assignments
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
        
        # Write/Delete permissions for staff
        return request.user.is_staff


class ReadOnlyForUsers(permissions.BasePermission):
    """
    Permission that allows read-only access for regular users
    and full access for staff
    """
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff) 