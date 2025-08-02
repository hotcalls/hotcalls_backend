from rest_framework import permissions


class CalendarPermission(permissions.BasePermission):
    """
    Custom permission for Calendar operations
    - Users can view calendars in their workspaces
    - Users can create/modify/delete calendars in their own workspaces
    - Staff can view and manage all calendars
    - Superusers have full control over all calendars
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
        
        # Write permissions (PUT, PATCH, POST, DELETE)
        if request.method in ['PUT', 'PATCH', 'POST', 'DELETE']:
            # Users can modify/delete calendars in their own workspaces, staff can modify all
            if obj.workspace:
                return (request.user in obj.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        return False


class CalendarConfigurationPermission(permissions.BasePermission):
    """
    Custom permission for CalendarConfiguration operations
    - Users can view configurations for calendars in their workspaces
    - Users can create/modify/delete configurations for calendars in their own workspaces
    - Staff can view and manage all configurations
    """
    
    def has_permission(self, request, view):
        # All authenticated users can access configuration operations
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Allow GET, POST, PUT, PATCH, DELETE for authenticated users
        return True
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            # Users can view configurations for calendars in their workspaces
            if obj.calendar.workspace:
                return (request.user in obj.calendar.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        # Write permissions (PUT, PATCH, POST, DELETE)
        if request.method in ['PUT', 'PATCH', 'POST', 'DELETE']:
            # Users can modify/delete configurations for calendars in their own workspaces
            if obj.calendar.workspace:
                return (request.user in obj.calendar.workspace.users.all() or 
                       request.user.is_staff)
            return request.user.is_staff
        
        return False 