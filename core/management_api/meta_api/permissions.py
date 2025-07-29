from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from core.models import Workspace

User = get_user_model()


class MetaIntegrationPermission(IsAuthenticated):
    """
    Permission class for Meta integration endpoints.
    
    Requires:
    - User must be authenticated
    - User must have email verified
    - User must belong to the workspace for workspace-specific operations
    """
    
    def has_permission(self, request, view):
        # Check basic authentication and email verification
        if not super().has_permission(request, view):
            return False
            
        if not request.user.is_email_verified:
            return False
            
        return True
    
    def has_object_permission(self, request, view, obj):
        """Check if user has permission for specific Meta integration object"""
        # Staff and superusers have full access
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Check if user belongs to the workspace
        if hasattr(obj, 'workspace'):
            return obj.workspace in request.user.mapping_user_workspaces.all()
        elif hasattr(obj, 'meta_integration'):
            return obj.meta_integration.workspace in request.user.mapping_user_workspaces.all()
        
        return False


class MetaWebhookPermission:
    """
    Special permission class for Meta webhook endpoints.
    These endpoints are called by Meta directly and don't require authentication.
    """
    
    def has_permission(self, request, view):
        # Webhook endpoints are public but will validate Meta signatures
        return True 