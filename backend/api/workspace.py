from typing import Optional

from .models import Workspace, WorkspaceMember


def resolve_workspace_membership_for_request(request) -> Optional[WorkspaceMember]:
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

        return memberships.filter(workspace_id=workspace_id_int).first()

    membership = memberships.order_by("workspace_id").first()
    if membership:
        return membership

    default_workspace = Workspace.objects.filter(slug="team-workspace").first()
    if default_workspace:
        membership, _ = WorkspaceMember.objects.get_or_create(
            user=request.user,
            workspace=default_workspace,
            defaults={"role": WorkspaceMember.ROLE_VIEWER},
        )
        return membership

    return None


def resolve_workspace_for_request(request) -> Optional[Workspace]:
    membership = resolve_workspace_membership_for_request(request)
    return membership.workspace if membership else None
