from rest_framework import permissions
from core.models import Agent
from core.management_api.calendar_api.permissions import CalendarLiveKitPermission


class AgentKnowledgePermission(permissions.BasePermission):
    """
    Permission for managing an agent's knowledge base.

    - Auth required
    - Read/List: users in the agent's workspace or staff
    - Write/Delete/Presign/Rebuild: users in the agent's workspace or staff
    """

    def has_permission(self, request, view):
        # Allow if request has a valid LiveKit token (bypasses Django auth)
        try:
            livekit_perm = CalendarLiveKitPermission()
            if livekit_perm._is_valid_livekit_request(request):  # type: ignore[attr-defined]
                return True
        except Exception:
            # Fall back to standard handling if LiveKit check fails for any reason
            pass

        # Otherwise require normal Django auth
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj: Agent):
        # LiveKit-authenticated requests get full object access
        try:
            livekit_perm = CalendarLiveKitPermission()
            if livekit_perm._is_valid_livekit_request(request):  # type: ignore[attr-defined]
                return True
        except Exception:
            pass

        # Regular Django auth logic for non-LiveKit requests
        if request.user.is_staff:
            return True
        return request.user in obj.workspace.users.all()


class PublicAgentKnowledgePermission(permissions.BasePermission):
    """
    Public permission class for presign URLs - allows unauthenticated access.
    """

    def has_permission(self, request, view):
        # Allow all requests (no authentication required)
        return True

    def has_object_permission(self, request, view, obj: Agent):
        # Allow all requests (no authentication required)
        return True



