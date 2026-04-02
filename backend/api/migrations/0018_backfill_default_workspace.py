from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    Workspace = apps.get_model("api", "Workspace")
    WorkspaceMember = apps.get_model("api", "WorkspaceMember")
    McapLog = apps.get_model("api", "McapLog")
    ExportJob = apps.get_model("api", "ExportJob")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    workspace, _ = Workspace.objects.get_or_create(
        slug="team-workspace",
        defaults={"name": "Team Workspace", "is_active": True},
    )

    McapLog.objects.filter(workspace__isnull=True).update(workspace=workspace)
    ExportJob.objects.filter(workspace__isnull=True).update(workspace=workspace)

    for user in User.objects.all().iterator():
        role = "admin" if (user.is_staff or user.is_superuser) else "viewer"
        WorkspaceMember.objects.get_or_create(
            user=user,
            workspace=workspace,
            defaults={"role": role},
        )


def backward(apps, schema_editor):
    Workspace = apps.get_model("api", "Workspace")
    WorkspaceMember = apps.get_model("api", "WorkspaceMember")
    McapLog = apps.get_model("api", "McapLog")
    ExportJob = apps.get_model("api", "ExportJob")

    workspace = Workspace.objects.filter(slug="team-workspace").first()
    if workspace is None:
        return

    McapLog.objects.filter(workspace=workspace).update(workspace=None)
    ExportJob.objects.filter(workspace=workspace).update(workspace=None)
    WorkspaceMember.objects.filter(workspace=workspace).delete()
    workspace.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0017_workspace_exportjob_created_by_mcaplog_created_by_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
