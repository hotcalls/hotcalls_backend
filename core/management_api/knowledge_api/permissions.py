from rest_framework import permissions
from core.models import Agent


class AgentKnowledgePermission(permissions.BasePermission):
    """
    Permission for managing an agent's knowledge base.

    - Auth required
    - Read/List: users in the agent's workspace or staff
    - Write/Delete/Presign/Rebuild: users in the agent's workspace or staff
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj: Agent):
        if request.user.is_staff:
            return True
        return request.user in obj.workspace.users.all()


