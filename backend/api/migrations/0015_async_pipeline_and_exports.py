from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0014_mcaplog_map_preview_uri"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcaplog",
            name="gps_error",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mcaplog",
            name="gps_status",
            field=models.CharField(default="pending", max_length=255),
        ),
        migrations.AddField(
            model_name="mcaplog",
            name="map_preview_error",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mcaplog",
            name="map_preview_status",
            field=models.CharField(default="pending", max_length=255),
        ),
        migrations.CreateModel(
            name="ExportJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("format", models.CharField(max_length=20)),
                ("status", models.CharField(default="pending", max_length=20)),
                ("requested_ids", models.JSONField(blank=True, default=list)),
                ("zip_uri", models.CharField(blank=True, max_length=500, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="ExportItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("status", models.CharField(default="pending", max_length=20)),
                ("output_uri", models.CharField(blank=True, max_length=500, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("attempts", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="api.exportjob",
                    ),
                ),
                (
                    "mcap_log",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="api.mcaplog",
                    ),
                ),
            ],
            options={
                "unique_together": {("job", "mcap_log")},
            },
        ),
    ]
