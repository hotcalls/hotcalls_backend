from rest_framework import permissions


class CallLogPermission(permissions.BasePermission):
    """
    Custom permission for CallLog operations
    - All authenticated users can view call logs
    - Only staff can create/modify call logs
    - Only superusers can delete call logs
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


class CallLogAnalyticsPermission(permissions.BasePermission):
    """
    Permission for call analytics
    - All authenticated users can view analytics
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated 