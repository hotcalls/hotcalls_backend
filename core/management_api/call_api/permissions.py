from rest_framework import permissions
import os


class CallLogPermission(permissions.BasePermission):
    """
    Custom permission for CallLog operations
    - ONLY LiveKit secret header authentication (X-LiveKit-CallLog-Secret)
    - No Django session/token authentication
    """
    
    def has_permission(self, request, view):
        # ONLY check for LiveKit secret header - no Django auth
        return self._is_valid_livekit_request(request)
    
    def has_object_permission(self, request, view, obj):
        # ONLY check for LiveKit secret header - no Django auth
        return self._is_valid_livekit_request(request)
    
    def _is_valid_livekit_request(self, request):
        """Check if request has valid LiveKit secret header"""
        webhook_secret = request.META.get('HTTP_X_LIVEKIT_CALLLOG_SECRET')
        expected_secret = os.getenv('CALL_LOG_SECRET', 'asfdafdasfJFDLJasdfljalfdhHDFDJHF32!!!')
        return webhook_secret == expected_secret


class CallLogAnalyticsPermission(permissions.BasePermission):
    """
    Permission for call analytics
    - All authenticated users can view analytics
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated 