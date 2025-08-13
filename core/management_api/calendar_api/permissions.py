from rest_framework import permissions
from core.models import LiveKitAgent


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


class CalendarLiveKitPermission(permissions.BasePermission):
    """
    Unified permission for Calendar APIs.
    - Primary path: LiveKit token via HTTP_X_LIVEKIT_TOKEN header (bypasses Django auth)
    - Otherwise: fall back to standard Django user auth for regular users
    """

    def has_permission(self, request, view):
        # Primary: allow requests authenticated via LiveKit token
        if self._is_valid_livekit_request(request):
            return True

        # Otherwise require normal Django auth
        if not (request.user and request.user.is_authenticated):
            return False

        # Read access for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True

        # Allow authenticated users to initiate Google OAuth flow
        if hasattr(view, 'action') and view.action in ['get_google_auth_url']:
            return True

        # Write access requires staff
        return request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # LiveKit requests get full object-level permissions
        if self._is_valid_livekit_request(request):
            return True

        # Regular Django auth logic for non-LiveKit requests
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        return request.user.is_staff

    def _is_valid_livekit_request(self, request) -> bool:
        """Validate LiveKit token header against LiveKitAgent tokens."""
        token = request.META.get('HTTP_X_LIVEKIT_TOKEN')
        if not token:
            return False
        try:
            agent = LiveKitAgent.objects.get(token=token)
            if not agent.is_valid():
                return False
            request.livekit_agent = agent
            return True
        except LiveKitAgent.DoesNotExist:
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