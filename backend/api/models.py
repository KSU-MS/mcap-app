from django.contrib.gis.db import models


class McapLog(models.Model):
    file_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    original_uri = models.TextField(null=True, blank=True)
    recovered_uri = models.CharField(default="pending")
    recovery_status = models.CharField(default="pending")
    parse_status = models.CharField(default="pending")
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
