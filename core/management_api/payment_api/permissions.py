from rest_framework import permissions
from core.models import Workspace


class WorkspacePaymentPermission(permissions.BasePermission):
    """
    Custom permission for workspace payment operations.
    Only workspace users can manage payment settings for their workspace.
    """
    
    def has_permission(self, request, view):
        # User must be authenticated
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Superusers can do everything
        if getattr(request.user, 'is_superuser', False):
            return True
        # For workspace objects
        if isinstance(obj, Workspace):
            # Check if user is member of this workspace
            return obj.users.filter(id=request.user.id).exists()
        
        # For other objects that have workspace field
        if hasattr(obj, 'workspace'):
            return obj.workspace.users.filter(id=request.user.id).exists()
        
        return False


class IsWorkspaceMember(permissions.BasePermission):
    """
    Permission to check if user is member of the workspace
    specified in the request (e.g., via query params or URL)
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Superusers can do everything
        if getattr(request.user, 'is_superuser', False):
            return True
        
        # Get workspace_id from different sources
        workspace_id = (
            view.kwargs.get('workspace_id') or 
            request.query_params.get('workspace_id') or
            request.data.get('workspace_id')
        )
        
        if not workspace_id:
            # Allow superusers above; non-superusers must provide workspace_id
            return False
        
        try:
            workspace = Workspace.objects.get(id=workspace_id)
            return workspace.users.filter(id=request.user.id).exists()
        except Workspace.DoesNotExist:
            return False
        
        return True 