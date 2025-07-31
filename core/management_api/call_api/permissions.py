from rest_framework import permissions
import os
from django.utils import timezone
from core.models import LiveKitAgent


class CallLogPermission(permissions.BasePermission):
    """
    Custom permission for CallLog operations
    - All authenticated users can view call logs (Django auth)
    - All authenticated users can make outbound calls (Django auth)
    - Only staff can create/modify call logs (Django auth)
    - Only superusers can delete call logs (Django auth)
    - LiveKit can also create call logs using X-LiveKit-Token header with valid agent tokens
    """
    
    def has_permission(self, request, view):
        # Check for LiveKit secret header first
        if self._is_valid_livekit_request(request):
            # LiveKit can create call logs but not read/update/delete
            if request.method == 'POST' and view.action == 'create':
                return True
            return False
        
        # All authenticated users need access for normal Django auth
        if not (request.user and request.user.is_authenticated):
            return False
            
        # Read operations for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Special case: make_outbound_call action is allowed for all authenticated users
        if view.action == 'make_outbound_call':
            return True
        
        # Other write operations require staff privileges
        return request.user.is_staff
    
    def has_object_permission(self, request, view, obj):
        # LiveKit requests don't get object-level permissions
        if self._is_valid_livekit_request(request):
            return False
            
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Write permissions for staff
        if request.method in ['PUT', 'PATCH']:
            return request.user.is_staff
        
        # Delete permissions only for superusers
        if request.method == 'DELETE':
            return request.user.is_superuser
        
        return False
    
    def _is_valid_livekit_request(self, request):
        """Check if request has valid LiveKit token header"""
        livekit_token = request.META.get('HTTP_X_LIVEKIT_TOKEN')
        
        if not livekit_token:
            return False
        
        try:
            # Find agent with this token
            agent = LiveKitAgent.objects.get(token=livekit_token)
            
            # Check if token is still valid (not expired)
            if not agent.is_valid():
                return False
            
            # Store agent info in request for potential use
            request.livekit_agent = agent
            return True
            
        except LiveKitAgent.DoesNotExist:
            return False


class CallLogAnalyticsPermission(permissions.BasePermission):
    """
    Permission for call analytics
    - All authenticated users can view analytics
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class CallTaskPermission(permissions.BasePermission):
    """
    Permission class for CallTask viewset
    
    - Superusers: Full access (CRUD + trigger)
    - Staff: Read access only  
    - Regular users: Read access only
    """
    
    def has_permission(self, request, view):
        # Everyone authenticated can read
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Only superusers can create, update, delete
        return request.user.is_superuser
    
    def has_object_permission(self, request, view, obj):
        # Everyone authenticated can read
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Only superusers can modify
        return request.user.is_superuser 