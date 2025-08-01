from rest_framework.permissions import BasePermission


class PlanAPIPermissions(BasePermission):
    """
    Permissions für Plan API
    
    - Pläne sind öffentlich lesbar (für Frontend/Marketing)
    - Schreibzugriff nur für Admins (über Django Admin)
    """
    
    def has_permission(self, request, view):
        """Basis-Permission Check"""
        # Lesezugriff für alle
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Schreibzugriff nur für Staff/Admins
        return request.user and request.user.is_staff
    
    def has_object_permission(self, request, view, obj):
        """Objekt-spezifische Permissions"""
        # Lesezugriff für alle
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Schreibzugriff nur für Staff/Admins
        return request.user and request.user.is_staff


class PublicReadPermission(BasePermission):
    """
    Einfache Permission: Öffentlich lesbar
    Für Plan-Informationen die jeder sehen können soll
    """
    
    def has_permission(self, request, view):
        return request.method in ['GET', 'HEAD', 'OPTIONS'] 