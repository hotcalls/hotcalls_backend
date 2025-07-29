from rest_framework.permissions import BasePermission


class VoicePermission(BasePermission):
    """
    Voice management permissions - Staff only access
    
    **🔐 Permission Requirements:**
    - **❌ Regular Users**: No access to voice management
    - **✅ Staff Members**: Full CRUD operations on voices
    - **✅ Superusers**: Full CRUD operations on voices
    
    **🎯 Security Rationale:**
    - Voice configurations are critical system resources
    - Only administrative staff should manage voice settings
    - Prevents unauthorized voice configuration changes
    """
    
    def has_permission(self, request, view):
        """Check if user has permission to access voice operations"""
        # Read operations: ALL users (including anonymous)
        # Write operations: Staff only
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Write operations require staff privileges
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_staff
        )
    
    def has_object_permission(self, request, view, obj):
        """Check if user has permission to access specific voice object"""
        # Read operations: ALL users (including anonymous)
        # Write operations: Staff only
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Write operations require staff privileges
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_staff
        ) 