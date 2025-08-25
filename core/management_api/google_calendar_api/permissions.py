"""Permissions for Google Calendar API"""
from rest_framework import permissions


class GoogleCalendarPermission(permissions.BasePermission):
    """
    Permission class for Google Calendar operations.
    - Users can only access calendars in their workspaces
    - Superusers can access all calendars
    """
    
    def has_permission(self, request, view):
        """Check if user has permission to access the view"""
        # User must be authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Email must be verified
        if not request.user.email_verified:
            return False
        
        return True
    
    def has_object_permission(self, request, view, obj):
        """Check if user has permission to access specific Google calendar"""
        # Superusers can access everything
        if request.user.is_superuser:
            return True
        
        # Check if user has access to the workspace
        return obj.calendar.workspace.users.filter(id=request.user.id).exists()
