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
    Permission class for Google Calendar MCP agents using PURE token-based authentication.
    
    **🔑 MCP Authentication (Primary):**
    - Uses HTTP_X_GOOGLE_MCP_TOKEN header for authentication
    - Validates token against core_google_calendar_mcp_agent table
    - NO Django user authentication required for MCP requests
    - Grants full access when valid MCP token is provided
    
    **👤 Fallback Authentication (Secondary):**
    - Falls back to normal Django authentication for non-MCP requests
    - Maintains backward compatibility for regular users
    """
    
    def has_permission(self, request, view):
        # PRIMARY: Check for MCP token authentication first
        if self._is_valid_mcp_request(request):
            # MCP token valid - grant full access, NO Django auth needed
            return True
        
        # FALLBACK: Only check Django auth if NOT an MCP request
        # This allows MCP to completely bypass Django authentication
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Regular Django auth logic for non-MCP requests
        if request.method in permissions.SAFE_METHODS:
            return True
        
        return request.user.is_staff
    
    def has_object_permission(self, request, view, obj):
        # PRIMARY: MCP requests get full object-level permissions
        if self._is_valid_mcp_request(request):
            # MCP token grants full access to all objects
            return True
            
        # FALLBACK: Regular Django auth logic for non-MCP requests
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return request.user.is_staff
    
    def _is_valid_mcp_request(self, request):
        """
        Check if request has valid Google Calendar MCP token.
        
        **🔍 Token Validation Process:**
        1. Extract HTTP_X_GOOGLE_MCP_TOKEN from headers
        2. Query core_google_calendar_mcp_agent table for matching token
        3. Verify token has not expired (expires_at > now)
        4. Store agent info in request for potential logging
        
        **✅ Returns True:** Valid MCP token found and not expired
        **❌ Returns False:** No token, invalid token, or expired token
        """
        mcp_token = request.META.get('HTTP_X_GOOGLE_MCP_TOKEN')
        
        if not mcp_token:
            return False
        
        try:
            from core.models import GoogleCalendarMCPAgent
            
            # Find MCP agent with this token (SQL query to core_google_calendar_mcp_agent)
            agent = GoogleCalendarMCPAgent.objects.get(token=mcp_token)
            
            # Check if token is still valid (not expired)
            if not agent.is_valid():
                return False
            
            # Store agent info in request for potential use/logging
            request.google_mcp_agent = agent
            return True
            
        except GoogleCalendarMCPAgent.DoesNotExist:
            return False
        except Exception as e:
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