from rest_framework import serializers
from .models import McapLog


def _normalize_string_array(values):
    if not isinstance(values, list):
        raise serializers.ValidationError("Expected a list of strings.")

    seen = set()
    normalized = []
    for value in values:
        if not isinstance(value, str):
            raise serializers.ValidationError("All items must be strings.")
        item = value.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


class McapLogSerializer(serializers.ModelSerializer):
    file = serializers.FileField(
        write_only=True, required=False, help_text="MCAP file to upload and parse"
    )
    file_name = serializers.CharField(required=False, allow_blank=True)
    cars = serializers.ListField(child=serializers.CharField(), required=False)
    drivers = serializers.ListField(child=serializers.CharField(), required=False)
    event_types = serializers.ListField(child=serializers.CharField(), required=False)
    locations = serializers.ListField(child=serializers.CharField(), required=False)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    map_data_available = serializers.SerializerMethodField()

    class Meta:
        model = McapLog
        fields = [
            "id",
            "file_name",
            "created_at",
            "original_uri",
            "recovered_uri",
            "recovery_status",
            "parse_status",
            "parse_task_id",
            "captured_at",
            "start_time",
            "end_time",
            "duration_seconds",
            "channel_count",
            "channels",
            "file_size",
            "lap_path",
            "notes",
            "tags",
            "cars",
            "drivers",
            "event_types",
            "locations",
            "map_preview_uri",
            "map_data_available",
            "file",
        ]

    def get_map_data_available(self, obj):
        return bool(obj.lap_path)

    def validate_tags(self, value):
        return _normalize_string_array(value)

    def validate_cars(self, value):
        return _normalize_string_array(value)

    def validate_drivers(self, value):
        return _normalize_string_array(value)

    def validate_event_types(self, value):
        return _normalize_string_array(value)

    def validate_locations(self, value):
        return _normalize_string_array(value)


class ParseSummaryRequestSerializer(serializers.Serializer):
    path = serializers.CharField()


class DownloadRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of MCAP log IDs to download",
    )
    format = serializers.ChoiceField(
        choices=["mcap", "csv_omni", "csv_tvn", "ld"],
        default="mcap",
        required=False,
        help_text="Output format: 'mcap' for original files, 'csv_omni', 'csv_tvn', or 'ld' for conversion",
    )
