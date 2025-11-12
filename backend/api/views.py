from rest_framework import viewsets
from .models import McapLog
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import McapLogSerializer , ParseSummaryRequestSerializer
from .parser import Parser
from .gpsparse import GpsParser
import os
import datetime
from django.utils import timezone
from django.contrib.gis.geos import Point, LineString
from django.conf import settings

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
                    
                    # Note: location field is for user-tagged locations and can be set manually
                    # In the future, it could be auto-populated from lap_path (e.g., start point, end point, or significant point)
                
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


class ParseSummaryView(APIView):
    def post(self, request):
        serializer = ParseSummaryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        path = serializer.validated_data["path"]

        # Call your existing parsing function here:
        result = Parser.parse_stuff(path)  # your Python parser returning a dict

        return Response(result, status=status.HTTP_200_OK)
