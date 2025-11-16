from rest_framework import serializers
from .models import McapLog, Car, Driver, EventType

class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = ['id', 'name']

class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['id', 'name']

class EventTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventType
        fields = ['id', 'name']

class McapLogSerializer(serializers.ModelSerializer):
    # Read: return nested objects, Write: accept IDs
    car = CarSerializer(read_only=True, allow_null=True)
    driver = DriverSerializer(read_only=True, allow_null=True)
    event_type = EventTypeSerializer(read_only=True, allow_null=True)
    
    # For write operations, accept IDs via car_id, driver_id, event_type_id
    car_id = serializers.PrimaryKeyRelatedField(
        queryset=Car.objects.all(), 
        source='car',
        write_only=True, 
        allow_null=True, 
        required=False
    )
    driver_id = serializers.PrimaryKeyRelatedField(
        queryset=Driver.objects.all(), 
        source='driver',
        write_only=True, 
        allow_null=True, 
        required=False
    )
    event_type_id = serializers.PrimaryKeyRelatedField(
        queryset=EventType.objects.all(), 
        source='event_type',
        write_only=True, 
        allow_null=True, 
        required=False
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
                  'lap_path',
                  'car',
                  'driver',
                  'event_type',
                  'car_id',
                  'driver_id',
                  'event_type_id',
                  'notes',
                  'file'
                  ]
        
class ParseSummaryRequestSerializer(serializers.Serializer):
    path = serializers.CharField()
    

