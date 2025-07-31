from rest_framework import permissions


class SuperuserOnlyPermission(permissions.BasePermission):
    """
    Permission class that only allows superusers to access the endpoint.
    Staff members are explicitly excluded.
    """
    
    def has_permission(self, request, view):
        """
        Only superusers can access LiveKit token generation
        Staff members are NOT allowed
        """
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_superuser
        ) 