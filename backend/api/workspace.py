from typing import Optional

from .models import Workspace, WorkspaceMember


def resolve_workspace_for_request(request) -> Optional[Workspace]:
    if not request.user or not request.user.is_authenticated:
        return None

    workspace_id = request.query_params.get("workspace_id") or request.headers.get(
        "X-Workspace-Id"
    )

    memberships = WorkspaceMember.objects.filter(user=request.user).select_related(
        "workspace"
    )

    if workspace_id:
        try:
            workspace_id_int = int(workspace_id)
        except (TypeError, ValueError):
            return None

        membership = memberships.filter(workspace_id=workspace_id_int).first()
        return membership.workspace if membership else None

    membership = memberships.order_by("workspace_id").first()
    if membership:
        return membership.workspace

    default_workspace = Workspace.objects.filter(slug="team-workspace").first()
    if default_workspace:
        WorkspaceMember.objects.get_or_create(
            user=request.user,
            workspace=default_workspace,
            defaults={"role": WorkspaceMember.ROLE_VIEWER},
        )
        return default_workspace

    return None
