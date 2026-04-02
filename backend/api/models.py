from django.contrib.gis.db import models
from django.conf import settings


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class WorkspaceMember(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_VIEWER, "Viewer"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "workspace")


class McapLog(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mcap_logs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_mcap_logs",
    )
    file_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    original_uri = models.TextField(null=True, blank=True)
    recovered_uri = models.CharField(default="pending")
    recovery_status = models.CharField(default="pending")
    parse_status = models.CharField(default="pending")
    gps_status = models.CharField(default="pending", max_length=255)
    gps_error = models.TextField(null=True, blank=True)
    map_preview_status = models.CharField(default="pending", max_length=255)
    map_preview_error = models.TextField(null=True, blank=True)
    parse_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Celery task ID for parsing job",
    )
    captured_at = models.DateTimeField(null=True)
    start_time = models.FloatField(null=True, help_text="Unix timestamp in seconds")
    end_time = models.FloatField(null=True, help_text="Unix timestamp in seconds")
    duration_seconds = models.FloatField(null=True)
    channel_count = models.IntegerField(default=0)
    channels = models.JSONField(
        default=list, blank=True, help_text="List of channel names"
    )
    file_size = models.BigIntegerField(
        null=True, blank=True, help_text="File size in bytes"
    )
    lap_path = models.LineStringField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        help_text="GPS path as LineString for map preview",
    )
    notes = models.TextField(blank=True, null=True)
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="User-defined tags for filtering (e.g. bell crank testing, other test)",
    )
    cars = models.JSONField(
        default=list, blank=True, help_text="User-defined car labels for filtering"
    )
    drivers = models.JSONField(
        default=list, blank=True, help_text="User-defined driver labels for filtering"
    )
    event_types = models.JSONField(
        default=list,
        blank=True,
        help_text="User-defined event type labels for filtering",
    )
    locations = models.JSONField(
        default=list, blank=True, help_text="User-defined location labels for filtering"
    )
    map_preview_uri = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Immutable SVG map preview URI",
    )


class ExportJob(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="export_jobs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_export_jobs",
    )
    format = models.CharField(max_length=20)
    resample_hz = models.FloatField(default=20.0)
    status = models.CharField(default="pending", max_length=20)
    requested_ids = models.JSONField(default=list, blank=True)
    zip_uri = models.CharField(max_length=500, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class ExportItem(models.Model):
    job = models.ForeignKey(ExportJob, on_delete=models.CASCADE, related_name="items")
    mcap_log = models.ForeignKey(McapLog, on_delete=models.CASCADE)
    status = models.CharField(default="pending", max_length=20)
    output_uri = models.CharField(max_length=500, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("job", "mcap_log")
