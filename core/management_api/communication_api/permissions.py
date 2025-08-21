from rest_framework import permissions

from core.management_api.calendar_api.permissions import CalendarLiveKitPermission


class LiveKitOrAuthenticatedWorkspaceUser(permissions.BasePermission):
    """Allow if request has a valid LiveKit token OR a logged-in user.

    Object-level checks must still enforce workspace membership.
    """

    def has_permission(self, request, view):
        # Try LiveKit path first
        livekit_perm = CalendarLiveKitPermission()
        if livekit_perm.has_permission(request, view):
            # If valid LiveKit token, allow
            return True
        # Otherwise require normal Django auth
        return bool(request.user and request.user.is_authenticated)


