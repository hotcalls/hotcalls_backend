from rest_framework import permissions


class CallLogPermission(permissions.BasePermission):
    """
    Custom permission for CallLog operations
    - All authenticated users can view call logs
    - All authenticated users can make outbound calls
    - Only staff can create/modify call logs (except outbound calls)
    - Only superusers can delete call logs
    """
    
    def has_permission(self, request, view):
        # All authenticated users need access
        if not (request.user and request.user.is_authenticated):
            return False
            
        # Read operations for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Special case: make_outbound_call action is allowed for all authenticated users
        if view.action == 'make_outbound_call':
            return True
        
        # Other write operations require staff privileges
        return request.user.is_staff
    
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


class CallTaskPermission(permissions.BasePermission):
    """
    Permission class for CallTask viewset
    
    - Superusers: Full access (CRUD + trigger)
    - Staff: Read access only  
    - Regular users: Read access only
    """
    
    def has_permission(self, request, view):
        # Everyone authenticated can read
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Only superusers can create, update, delete
        return request.user.is_superuser
    
    def has_object_permission(self, request, view, obj):
        # Everyone authenticated can read
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Only superusers can modify
        return request.user.is_superuser 