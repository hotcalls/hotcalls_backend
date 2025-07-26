from rest_framework import permissions


class CalendarPermission(permissions.BasePermission):
    """
    Custom permission for Calendar operations
    - Users can view calendars in their workspaces
    - Users can create/modify calendars in their own workspaces (for Google Calendar integration)
    - Staff can view and manage all calendars
    - Only superusers can delete calendars
    """
    
    def has_permission(self, request, view):
        # All authenticated users can access calendar operations
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view calendars in their workspaces, staff can view all
            if obj.workspace:
                return (request.user in obj.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Write permissions (PUT, PATCH, POST)
        if request.method in ['PUT', 'PATCH', 'POST']:
            # Users can modify calendars in their own workspaces, staff can modify all
            if obj.workspace:
                return (request.user in obj.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
        return False


class CalendarConfigurationPermission(permissions.BasePermission):
    """
    Custom permission for CalendarConfiguration operations
    - Users can view configurations for calendars in their workspaces
    - Users can create/modify configurations for calendars in their own workspaces
    - Staff can view and manage all configurations
    - Staff can delete configurations
    """
    
    def has_permission(self, request, view):
        # All authenticated users can access configuration operations
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view configurations for calendars in their workspaces
            if obj.calendar.workspace:
                return (request.user in obj.calendar.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Write permissions (PUT, PATCH, POST)
        if request.method in ['PUT', 'PATCH', 'POST']:
            # Users can modify configurations for calendars in their own workspaces
            if obj.calendar.workspace:
                return (request.user in obj.calendar.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Delete permissions for staff and superusers
        if request.method == 'DELETE':
            return request.user.is_staff
        
        return False 