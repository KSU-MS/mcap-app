from django.contrib.gis.db import models
from django.contrib.gis.geos import Point


class Car(models.Model):
    name = models.CharField(max_length=100,unique=True)

    def __str__(self):
        return self.name
    
class Driver(models.Model):
    name = models.CharField(max_length=100,unique=True)

    def __str__(self):
        return self.name
        
class EventType(models.Model):
    name = models.CharField(max_length=100,unique=True)

    def __str__(self):
        return self.name

class McapLog(models.Model):
    file_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    original_uri = models.TextField(null=True, blank=True)
    recovered_uri = models.CharField(default="pending")
    recovery_status = models.CharField(default="pending")
    parse_status = models.CharField(default="pending")
    captured_at = models.DateTimeField(null=True)
    start_time = models.FloatField(null=True, help_text="Unix timestamp in seconds")
    end_time = models.FloatField(null=True, help_text="Unix timestamp in seconds")
    duration_seconds = models.FloatField(null=True)
    channel_count = models.IntegerField(default=0)
    channels = models.JSONField(default=list, blank=True, help_text="List of channel names")
    location = models.PointField(geography=True, srid=4326, null=True, blank=True, help_text="GPS location (latitude, longitude)")
    notes = models.TextField(blank=True, null=True)

    car = models.ForeignKey(Car, null=True, blank=True, on_delete=models.SET_NULL)
    driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.ForeignKey(EventType, null=True, blank=True, on_delete=models.SET_NULL)
