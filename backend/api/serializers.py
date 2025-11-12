from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import McapLog, Car, Driver, EventType

class McapLogSerializer(serializers.ModelSerializer):
    car = serializers.PrimaryKeyRelatedField(
        queryset=Car.objects.all(), allow_null=True, required=False
    )
    driver = serializers.PrimaryKeyRelatedField(
        queryset=Driver.objects.all(), allow_null=True, required=False
    )
    event_type = serializers.PrimaryKeyRelatedField(
        queryset=EventType.objects.all(), allow_null=True, required=False
    )
    file = serializers.FileField(write_only=True, required=False, help_text="MCAP file to upload and parse")
    file_name = serializers.CharField(required=False, allow_blank=True)
    
    
    class Meta:
        model = McapLog
        fields = ['id',
                  'file_name',
                  'created_at',
                  'original_uri',
                  'recovered_uri',
                  'recovery_status',
                  'parse_status',
                  'captured_at',
                  'start_time',
                  'end_time',
                  'duration_seconds',
                  'channel_count',
                  'channels',
                  'location',
                  'car',
                  'driver',
                  'event_type',
                  'notes',
                  'file'
                  ]
        
class ParseSummaryRequestSerializer(serializers.Serializer):
    path = serializers.CharField()
    

