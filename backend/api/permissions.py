from rest_framework.permissions import BasePermission

from .models import WorkspaceMember
from .workspace import resolve_workspace_membership_for_request


class IsOwnerOrSharedUserResource(BasePermission):
    """Allow access to resources owned by request.user or shared (user=None)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, "user_id", None)
        return owner_id is None or owner_id == request.user.id


class IsWorkspaceMember(BasePermission):
    def has_permission(self, request, view):
        membership = resolve_workspace_membership_for_request(request)
        if membership is None:
            return False
        view.workspace = membership.workspace
        view.workspace_membership = membership
        return True


class HasWorkspaceWriteAccess(BasePermission):
    EDITOR_ROLES = {WorkspaceMember.ROLE_ADMIN, WorkspaceMember.ROLE_EDITOR}
    VIEWER_ALLOWED_ACTIONS = {
        "list",
        "retrieve",
        "geojson",
        "download",
        "job_status",
        "job_statuses",
        "tag_names",
        "car_names",
        "driver_names",
        "event_type_names",
        "location_names",
        "channel_names",
        "export_status",
        "export_download",
        "active_exports",
    }

    def has_permission(self, request, view):
        membership = getattr(view, "workspace_membership", None)
        if membership is None:
            membership = resolve_workspace_membership_for_request(request)
            if membership is None:
                return False
            view.workspace = membership.workspace
            view.workspace_membership = membership

        action = getattr(view, "action", None)
        if action in self.VIEWER_ALLOWED_ACTIONS:
            return True

        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return True

        return membership.role in self.EDITOR_ROLES
