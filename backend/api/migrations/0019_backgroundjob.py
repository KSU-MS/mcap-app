import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0018_backfill_default_workspace"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackgroundJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "job_type",
                    models.CharField(
                        choices=[
                            ("ingest_pipeline", "Ingest pipeline"),
                            ("export_job", "Export job"),
                            ("map_preview", "Map preview"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True, default="")),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=3)),
                (
                    "available_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="backgroundjob",
            index=models.Index(
                fields=["status", "available_at", "created_at"],
                name="api_backgro_status_d5010e_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="backgroundjob",
            index=models.Index(
                fields=["job_type", "status", "available_at"],
                name="api_backgro_job_typ_14638d_idx",
            ),
        ),
    ]
