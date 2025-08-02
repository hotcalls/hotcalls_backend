from rest_framework import permissions
from core.models import GoogleCalendarMCPAgent


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


class GoogleCalendarMCPPermission(permissions.BasePermission):
    """
    Permission class for Google Calendar MCP agents using token-based authentication.
    Similar to LiveKit agent authentication but for Google Calendar MCP.
    """
    
    def has_permission(self, request, view):
        # Check for MCP token header first
        if self._is_valid_mcp_request(request):
            return True
        
        # Fallback to regular authentication for other requests
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Read operations: authenticated users can access
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write operations require appropriate permissions
        return request.user.is_staff
    
    def has_object_permission(self, request, view, obj):
        # MCP requests don't get object-level permissions
        if self._is_valid_mcp_request(request):
            return True
            
        # Regular authentication logic
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write permissions for staff
        return request.user.is_staff
    
    def _is_valid_mcp_request(self, request):
        """Check if request has valid Google Calendar MCP token header"""
        mcp_token = request.META.get('HTTP_X_GOOGLE_MCP_TOKEN')
        
        if not mcp_token:
            return False
        
        try:
            # Find MCP agent with this token
            agent = GoogleCalendarMCPAgent.objects.get(token=mcp_token)
            
            # Check if token is still valid (not expired)
            if not agent.is_valid():
                return False
            
            # Store agent info in request for potential use
            request.google_mcp_agent = agent
            return True
            
        except GoogleCalendarMCPAgent.DoesNotExist:
            return False


class SuperuserOnlyPermission(permissions.BasePermission):
    """
    Permission class that only allows superusers to access the endpoint.
    Used for MCP token management.
    """
    
    def has_permission(self, request, view):
        """
        Only superusers can access MCP token generation
        Staff members are NOT allowed
        """
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_superuser
        ) 