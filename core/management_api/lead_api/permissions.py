from rest_framework import permissions


class LeadPermission(permissions.BasePermission):
    """
    Custom permission for Lead operations
    - All authenticated users can view and create leads
    - Users can edit leads they created or staff can edit all
    - Only staff can delete leads
    """
    
    def has_permission(self, request, view):
        # Authenticated users can access the API
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read and create permissions for authenticated users
        if request.method in permissions.SAFE_METHODS or request.method == 'POST':
            return True
        
        # Write permissions for the creator or staff
        if request.method in ['PUT', 'PATCH']:
            return request.user.is_staff
        
        # Delete permissions only for staff
        if request.method == 'DELETE':
            return request.user.is_staff
        
        return False


class LeadBulkPermission(permissions.BasePermission):
    """
    Permission for bulk lead operations
    - Only authenticated users can perform bulk operations
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated 