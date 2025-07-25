from rest_framework import permissions


class CalendarPermission(permissions.BasePermission):
    """
    Custom permission for Calendar operations
    - Users can view calendars in their workspaces
    - Staff can view all calendars
    - Only staff can create/modify calendars
    - Only superusers can delete calendars
    """
    
    def has_permission(self, request, view):
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write operations (create/update) require staff privileges
        return (request.user and 
                request.user.is_authenticated and 
                request.user.is_staff)
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view calendars in their workspaces, staff can view all
            if obj.workspace:
                return (request.user in obj.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Write permissions (PUT, PATCH, POST) only for staff
        if request.method in ['PUT', 'PATCH', 'POST']:
            return request.user.is_staff
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
        return False


class CalendarConfigurationPermission(permissions.BasePermission):
    """
    Custom permission for CalendarConfiguration operations
    - Users can view configurations for calendars in their workspaces
    - Staff can view all configurations
    - Only staff can create/modify configurations
    - Only staff can delete configurations
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
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view configurations for calendars in their workspaces
            if obj.calendar.workspace:
                return (request.user in obj.calendar.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Write/Delete permissions for staff
        return request.user.is_staff 