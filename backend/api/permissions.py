from rest_framework.permissions import BasePermission


class IsOwnerOrSharedUserResource(BasePermission):
    """Allow access to resources owned by request.user or shared (user=None)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, "user_id", None)
        return owner_id is None or owner_id == request.user.id
