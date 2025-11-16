from rest_framework import viewsets
from rest_framework.decorators import action
from .models import McapLog, Car, Driver, EventType
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import (
    McapLogSerializer, 
    ParseSummaryRequestSerializer,
    CarSerializer,
    DriverSerializer,
    EventTypeSerializer
)
from .parser import Parser
from .gpsparse import GpsParser
import os
import datetime
from django.utils import timezone
from django.contrib.gis.geos import LineString
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class McapLogViewSet(viewsets.ModelViewSet):
    queryset = McapLog.objects.all()
    serializer_class = McapLogSerializer
    
    def create(self, request, *args, **kwargs):
        """
        Create a new McapLog. If 'file' is uploaded, save it, parse it, and populate fields.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Handle file upload
        uploaded_file = request.FILES.get('file')
        saved_file_path = None
        
        if uploaded_file:
            # Create media directory if it doesn't exist
            media_dir = settings.MEDIA_ROOT / 'mcap_logs'
            media_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename to avoid conflicts
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{timestamp}_{uploaded_file.name}"
            file_path = media_dir / file_name
            
            # Save the uploaded file
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            saved_file_path = str(file_path)
            
            # Store the URI in original_uri
            serializer.validated_data['original_uri'] = f"{settings.MEDIA_URL}mcap_logs/{file_name}"
            # Set file_name from uploaded file if not already provided
            if 'file_name' not in serializer.validated_data or not serializer.validated_data.get('file_name'):
                serializer.validated_data['file_name'] = uploaded_file.name
            
            # Parse the uploaded file
            try:
                parsed_data = Parser.parse_stuff(saved_file_path)
                
                # Populate fields from parsed data
                serializer.validated_data['channels'] = parsed_data.get("channels", [])
                serializer.validated_data['channel_count'] = parsed_data.get("channel_count", 0)
                serializer.validated_data['start_time'] = parsed_data.get("start_time")
                serializer.validated_data['end_time'] = parsed_data.get("end_time")
                serializer.validated_data['duration_seconds'] = parsed_data.get("duration", 0)
                
                # Parse GPS coordinates from the file
                gps_data = GpsParser.parse_gps(saved_file_path)
                all_coordinates = gps_data.get("all_coordinates", [])
                
                # Create LineString from all GPS coordinates for map preview
                if all_coordinates:
                    # LineString takes a list of (x, y) tuples, which is [longitude, latitude] in our case
                    # all_coordinates is already in [longitude, latitude] format
                    serializer.validated_data['lap_path'] = LineString(all_coordinates, srid=4326)
                
                if parsed_data.get("start_time"):
                    # Convert timestamp to timezone-aware datetime
                    naive_dt = datetime.datetime.fromtimestamp(parsed_data.get("start_time"))
                    serializer.validated_data['captured_at'] = timezone.make_aware(naive_dt)
                
                serializer.validated_data['parse_status'] = "completed"
            except Exception as e:
                serializer.validated_data['parse_status'] = f"error: {str(e)}"
        else:
            # If no file uploaded, ensure file_name is set if provided in request
            if 'file_name' not in serializer.validated_data or not serializer.validated_data.get('file_name'):
                # Set a default file_name if not provided
                serializer.validated_data['file_name'] = 'unknown.mcap'
        
        # Remove 'file' from validated_data since it's not a model field
        serializer.validated_data.pop('file', None)
        
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @swagger_auto_schema(
        method='get',
        operation_description="Returns simplified LineString as GeoJSON. Reads from DB if available, otherwise parses from MCAP file. Uses PostGIS ST_SimplifyVW for simplification.",
        manual_parameters=[
            openapi.Parameter(
                'tolerance',
                openapi.IN_QUERY,
                description="Simplification tolerance in degrees (default: 0.0001, roughly 11 meters). Higher values result in more aggressive simplification.",
                type=openapi.TYPE_NUMBER,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="GeoJSON FeatureCollection with simplified LineString",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'type': openapi.Schema(type=openapi.TYPE_STRING, example='FeatureCollection'),
                        'features': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        ),
                    }
                )
            ),
            404: openapi.Response(description="No GPS path available for this log"),
            500: openapi.Response(description="Failed to parse MCAP file"),
        },
        tags=['MCAP Logs']
    )
    @action(detail=True, methods=['get'], url_path='geojson')
    def geojson(self, request, pk=None):
        """
        Returns simplified LineString as GeoJSON.
        Reads from DB if available, otherwise parses from MCAP file.
        Uses PostGIS ST_SimplifyVW for simplification.
        """
        mcap_log = self.get_object()
        
        # Get or parse lap_path
        lap_path = mcap_log.lap_path
        
        # If lap_path doesn't exist in DB, try to parse from MCAP file
        if not lap_path and mcap_log.original_uri:
            try:
                # Extract file path from original_uri
                # original_uri format: /media/mcap_logs/filename.mcap
                if mcap_log.original_uri.startswith(settings.MEDIA_URL):
                    file_name = mcap_log.original_uri.replace(settings.MEDIA_URL, '')
                    file_path = settings.MEDIA_ROOT / file_name
                    
                    if file_path.exists():
                        # Parse GPS coordinates from MCAP file
                        gps_data = GpsParser.parse_gps(str(file_path))
                        all_coordinates = gps_data.get("all_coordinates", [])
                        
                        if all_coordinates:
                            lap_path = LineString(all_coordinates, srid=4326)
                            # Optionally save to DB for future use
                            mcap_log.lap_path = lap_path
                            mcap_log.save(update_fields=['lap_path'])
            except Exception as e:
                return Response(
                    {'error': f'Failed to parse MCAP file: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        if not lap_path:
            return Response(
                {'error': 'No GPS path available for this log'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Simplify using PostGIS ST_SimplifyVW
        # Get tolerance parameter from query string (default: 0.0001 degrees, roughly 11 meters)
        tolerance = float(request.query_params.get('tolerance', 0.0001))
        
        try:
            # Use PostGIS ST_SimplifyVW function
            # Note: ST_SimplifyVW works with geometry, not geography, so we need to cast
            from django.contrib.gis.db.models import Func
            from django.contrib.gis.db.models.fields import GeometryField
            from django.db.models import F
            
            # Create a queryset with the simplified geometry
            # Cast geography to geometry using ::geometry, then simplify
            simplified_path = McapLog.objects.filter(pk=mcap_log.pk).annotate(
                geometry_path=Func(
                    F('lap_path'),
                    template='%(expressions)s::geometry',
                    output_field=GeometryField(srid=4326)
                ),
                simplified_path=Func(
                    F('geometry_path'),
                    tolerance,
                    function='ST_SimplifyVW',
                    output_field=GeometryField(srid=4326)
                )
            ).first().simplified_path
            
            # If simplification failed or returned None, use original
            if not simplified_path:
                simplified_path = lap_path
        except Exception as e:
            # Fallback: use original path if PostGIS function fails
            print(f"Warning: ST_SimplifyVW failed, using original path: {e}")
            simplified_path = lap_path
        
        # Build GeoJSON FeatureCollection
        import json
        features = []
        
        # Add simplified path as LineString
        if simplified_path:
            # Convert LineString to GeoJSON format
            coordinates = list(simplified_path.coords)
            path_feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': coordinates
                },
                'properties': {
                    'type': 'lap_path',
                    'id': mcap_log.id,
                    'simplified': True
                }
            }
            features.append(path_feature)
        
        # Return FeatureCollection
        geojson_response = {
            'type': 'FeatureCollection',
            'features': features
        }
        
        return Response(geojson_response, status=status.HTTP_200_OK)


class ParseSummaryView(APIView):
    @swagger_auto_schema(
        request_body=ParseSummaryRequestSerializer,
        operation_description="Parse MCAP file summary without creating a database record. Returns channel information, timestamps, and duration.",
        responses={
            200: openapi.Response(
                description="Parsed MCAP file summary",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'channels': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING)),
                        'channel_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'start_time': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'end_time': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'duration': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'formatted_date': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: openapi.Response(description="Invalid request data"),
        },
        tags=['Parsing']
    )
    def post(self, request):
        """
        Parse MCAP file summary without creating a database record.
        Returns channel information, timestamps, and duration.
        """
        serializer = ParseSummaryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        path = serializer.validated_data["path"]

        # Call your existing parsing function here:
        result = Parser.parse_stuff(path)  # your Python parser returning a dict

        return Response(result, status=status.HTTP_200_OK)


class CarViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Car instances.
    Provides list and detail views for dropdown population.
    """
    queryset = Car.objects.all().order_by('name')
    serializer_class = CarSerializer


class DriverViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Driver instances.
    Provides list and detail views for dropdown population.
    """
    queryset = Driver.objects.all().order_by('name')
    serializer_class = DriverSerializer


class EventTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing EventType instances.
    Provides list and detail views for dropdown population.
    """
    queryset = EventType.objects.all().order_by('name')
    serializer_class = EventTypeSerializer
