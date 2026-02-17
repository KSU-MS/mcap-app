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
    EventTypeSerializer,
    DownloadRequestSerializer
)
from .parser import Parser
from .gpsparse import GpsParser
from .tasks import parse_mcap_file, recover_mcap_file
import os
import datetime
import zipfile
import tempfile
from pathlib import Path
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.contrib.gis.geos import LineString, Point, Polygon
from django.conf import settings
from django.db.models import Q
from celery.result import AsyncResult

class McapLogViewSet(viewsets.ModelViewSet):
    queryset = McapLog.objects.all()
    serializer_class = McapLogSerializer
    
    def get_queryset(self):
        """
        Override DRF's get_queryset() to add custom filtering logic.
        
        This method is called automatically by DRF for list(), retrieve(), update(), etc.
        It does NOT need @action decorator because it's not an endpoint - it's an internal helper.
        
        Supported query parameters (all optional, can be combined):
        - search: Text search in file_name and notes (case-insensitive)
        - start_date: Filter logs captured on or after this date (YYYY-MM-DD)
        - end_date: Filter logs captured on or before this date (YYYY-MM-DD)
        - car_id: Filter by car ID (integer)
        - event_type_id: Filter by event type ID (integer)
        - driver_id: Filter by driver ID (integer)
        - parse_status: Filter by parse status (string, e.g., "completed", "pending")
        - recovery_status: Filter by recovery status (string)
        - location: Filter by geographic bounding box (format: min_lon,min_lat,max_lon,max_lat)
        - page: Page number for pagination (default: 1, handled by DRF pagination)
        
        Returns: Filtered queryset ordered by creation date (newest first)
        """
        # Start with all McapLog objects
        queryset = McapLog.objects.all()
        
        # ===== TEXT SEARCH =====
        # Search across log + FK names (case-insensitive partial match)
        # Example: ?search=race will find "race_log.mcap", notes containing "race",
        # or related car/driver/event_type names containing "race".
        search = self.request.query_params.get('search', None)
        if search:
            search = str(search).strip()
            if search:
                q = (
                    Q(file_name__icontains=search)
                    | Q(notes__icontains=search)
                    | Q(car__name__icontains=search)
                    | Q(driver__name__icontains=search)
                    | Q(event_type__name__icontains=search)
                )

                # If search is numeric, also match ID exactly
                try:
                    q = Q(id=int(search)) | q
                except (ValueError, TypeError):
                    pass

                queryset = queryset.filter(q)
        
        # ===== DATE RANGE FILTERING =====
        # Filter logs by capture date range using captured_at field
        # start_date: Include logs from this date onwards (start of day)
        start_date = self.request.query_params.get('start_date', None)
        if start_date:
            try:
                from django.utils.dateparse import parse_date
                date_obj = parse_date(start_date)
                if date_obj:
                    # Convert to start of day (00:00:00) with timezone awareness
                    start_datetime = timezone.make_aware(
                        datetime.datetime.combine(date_obj, datetime.time.min)
                    )
                    queryset = queryset.filter(captured_at__gte=start_datetime)
            except (ValueError, TypeError):
                pass  # Ignore invalid date formats silently
        
        # end_date: Include logs up to this date (end of day)
        end_date = self.request.query_params.get('end_date', None)
        if end_date:
            try:
                from django.utils.dateparse import parse_date
                date_obj = parse_date(end_date)
                if date_obj:
                    # Convert to end of day (23:59:59) with timezone awareness
                    end_datetime = timezone.make_aware(
                        datetime.datetime.combine(date_obj, datetime.time.max)
                    )
                    queryset = queryset.filter(captured_at__lte=end_datetime)
            except (ValueError, TypeError):
                pass  # Ignore invalid date formats silently
        
        # ===== FOREIGN KEY FILTERING =====
        # Filter by car (foreign key relationship)
        car_id = self.request.query_params.get('car_id', None)
        if car_id:
            try:
                queryset = queryset.filter(car_id=int(car_id))
            except (ValueError, TypeError):
                pass  # Ignore invalid car_id values
        
        # Filter by event type (foreign key relationship)
        event_type_id = self.request.query_params.get('event_type_id', None)
        if event_type_id:
            try:
                queryset = queryset.filter(event_type_id=int(event_type_id))
            except (ValueError, TypeError):
                pass  # Ignore invalid event_type_id values
        
        # Filter by driver (foreign key relationship)
        driver_id = self.request.query_params.get('driver_id', None)
        if driver_id:
            try:
                queryset = queryset.filter(driver_id=int(driver_id))
            except (ValueError, TypeError):
                pass  # Ignore invalid driver_id values
        
        # ===== STATUS FILTERING =====
        # Filter by parse status (e.g., "pending", "processing", "completed", "error:...")
        parse_status = self.request.query_params.get('parse_status', None)
        if parse_status:
            queryset = queryset.filter(parse_status=parse_status)
        
        # Filter by recovery status (e.g., "pending", "completed", "failed")
        recovery_status = self.request.query_params.get('recovery_status', None)
        if recovery_status:
            queryset = queryset.filter(recovery_status=recovery_status)
        
        # ===== GEOGRAPHIC LOCATION FILTERING =====
        # Filter logs by geographic bounding box (PostGIS spatial query)
        # Format: min_lon,min_lat,max_lon,max_lat (comma-separated)
        # Example: ?location=-122.5,37.7,-122.3,37.9
        # Returns logs whose lap_path (GPS LineString) intersects with the bounding box
        location = self.request.query_params.get('location', None)
        if location:
            try:
                # Parse comma-separated coordinates
                coords = [float(x.strip()) for x in location.split(',')]
                if len(coords) == 4:
                    min_lon, min_lat, max_lon, max_lat = coords
                    # Create bounding box polygon using PostGIS
                    bbox = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))
                    # Filter logs where lap_path intersects with bounding box
                    queryset = queryset.filter(lap_path__intersects=bbox)
            except (ValueError, TypeError, IndexError):
                pass  # Ignore invalid location formats silently
        
        # ===== CUSTOM TAG FILTERING =====
        # Filter logs that have the given tag in their tags array
        tag = self.request.query_params.get('tag', None)
        if tag:
            tag = str(tag).strip()
            if tag:
                queryset = queryset.filter(tags__contains=[tag])
        
        # ===== CHANNEL FILTERING =====
        # Filter logs that contain the given channel name in their channels array
        channel = self.request.query_params.get('channel', None)
        if channel:
            channel = str(channel).strip()
            if channel:
                queryset = queryset.filter(channels__contains=[channel])
        
        # Return filtered queryset ordered by creation date (newest first)
        # Pagination is handled automatically by DRF after this method returns
        return queryset.order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        """
        List MCAP logs with optional filtering.
        All query parameters are optional and can be combined.
        Examples:
        - /api/mcap-logs/?start_date=2025-01-01&end_date=2025-01-31
        - /api/mcap-logs/?car_id=1&event_type_id=2
        - /api/mcap-logs/?location=-122.5,37.7,-122.3,37.9
        """
        return super().list(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """
        Create a new McapLog. If 'file' is uploaded, save it, parse it, and populate fields.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Handle file upload
        uploaded_file = request.FILES.get('file')
        saved_file_relpath = None
        
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
            
            # Store relative path so Celery workers (possibly in Docker) can resolve via MEDIA_ROOT
            saved_file_relpath = str(file_path.relative_to(settings.MEDIA_ROOT))
            
            # Calculate and store file size
            file_size = file_path.stat().st_size
            serializer.validated_data['file_size'] = file_size
            
            # Store the URI in original_uri
            serializer.validated_data['original_uri'] = f"{settings.MEDIA_URL}mcap_logs/{file_name}"
            # Set file_name from uploaded file if not already provided
            if 'file_name' not in serializer.validated_data or not serializer.validated_data.get('file_name'):
                serializer.validated_data['file_name'] = uploaded_file.name
            
            # Set parse_status to pending - will be processed in background
            serializer.validated_data['parse_status'] = "pending"
        else:
            # If no file uploaded, ensure file_name is set if provided in request
            if 'file_name' not in serializer.validated_data or not serializer.validated_data.get('file_name'):
                # Set a default file_name if not provided
                serializer.validated_data['file_name'] = 'unknown.mcap'
        
        # Remove 'file' from validated_data since it's not a model field
        serializer.validated_data.pop('file', None)
        
        # Create the record first
        self.perform_create(serializer)
        mcap_log_instance = serializer.instance
        
        # If a file was uploaded, trigger recovery (which will trigger parsing when done)
        if saved_file_relpath:
            # Recovery task will trigger parsing automatically when it completes
            recovery_task = recover_mcap_file.delay(mcap_log_instance.id, saved_file_relpath)
            # Store the recovery task ID for status tracking
            mcap_log_instance.parse_task_id = recovery_task.id
            mcap_log_instance.save(update_fields=['parse_task_id'])
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=True, methods=['get'], url_path='geojson')
    def geojson(self, request, pk=None):
        """
        Returns LineString as GeoJSON.
        Reads from DB if available, otherwise parses from MCAP file.
        By default returns the full unsimplified path. Use ?simplify=true to enable simplification.
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
        
        # Check if simplification is requested
        simplify = request.query_params.get('simplify', 'false').lower() == 'true'
        
        if simplify:
            # Simplify using PostGIS ST_SimplifyVW
            # Get tolerance parameter from query string (default: 0.00001 degrees, roughly 1.1 meters)
            tolerance = float(request.query_params.get('tolerance', 0.00001))
            
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
        else:
            # Return full unsimplified path
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
                    'simplified': simplify
                }
            }
            features.append(path_feature)
        
        # Return FeatureCollection
        geojson_response = {
            'type': 'FeatureCollection',
            'features': features
        }
        
        return Response(geojson_response, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='download')
    def download(self, request):
        """
        Download selected MCAP log files as a ZIP archive.
        Accepts a POST request with a list of log IDs and optional format in the request body.
        Example: {"ids": [1, 2, 3], "format": "csv_omni"}
        Formats: "mcap" (default, original files), "csv_omni", "csv_tvn", "ld"
        """
        serializer = DownloadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        log_ids = serializer.validated_data['ids']
        output_format = serializer.validated_data.get('format', 'mcap')
        
        # Get the McapLog objects
        mcap_logs = McapLog.objects.filter(id__in=log_ids)
        
        if not mcap_logs.exists():
            return Response(
                {'error': 'No logs found with the provided IDs'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if all requested IDs were found
        found_ids = set(mcap_logs.values_list('id', flat=True))
        requested_ids = set(log_ids)
        missing_ids = requested_ids - found_ids
        
        if missing_ids:
            return Response(
                {'error': f'Log IDs not found: {list(missing_ids)}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Handle CSV/LD conversion
        if output_format.startswith('csv_') or output_format == 'ld':
            print(
                f"[download] CSV/LD conversion requested: ids={log_ids}, count={len(mcap_logs)}, format={output_format}"
            )
            return self._download_as_converted(mcap_logs, output_format)
        
        # Handle MCAP download (original behavior)
        return self._download_as_mcap(mcap_logs)
    
    def _download_as_converted(self, mcap_logs, format):
        """
        Convert MCAP files to CSV/LD and download as ZIP.
        Uses synchronous conversion (can be switched to async Celery if needed).
        """
        from .mcap_converter import McapToCsvConverter
        from django.conf import settings
        import datetime
        
        print(
            f"[download] CSV conversion started: format={format}, count={len(mcap_logs)}"
        )
        conversion_results = {}
        conversion_errors = []
        
        # Process conversions synchronously
        for mcap_log in mcap_logs:
            try:
                print(
                    f"[download] log id={mcap_log.id} file_name={mcap_log.file_name}"
                )
                # Determine source file path
                file_path = None
                
                # Try recovered_uri first if available and not pending
                if mcap_log.recovered_uri and mcap_log.recovered_uri != "pending":
                    if mcap_log.recovered_uri.startswith(settings.MEDIA_URL):
                        file_name = mcap_log.recovered_uri.replace(settings.MEDIA_URL, '', 1)
                        file_path = Path(settings.MEDIA_ROOT) / file_name
                    elif mcap_log.recovered_uri.startswith('/'):
                        file_path = Path(mcap_log.recovered_uri)
                    else:
                        file_path = Path(settings.MEDIA_ROOT) / mcap_log.recovered_uri
                
                # Fall back to original_uri if recovered_uri not available
                if not file_path or not file_path.exists():
                    if mcap_log.original_uri:
                        if mcap_log.original_uri.startswith(settings.MEDIA_URL):
                            file_name = mcap_log.original_uri.replace(settings.MEDIA_URL, '', 1)
                            file_path = Path(settings.MEDIA_ROOT) / file_name
                        elif mcap_log.original_uri.startswith('/'):
                            file_path = Path(mcap_log.original_uri)
                        else:
                            file_path = Path(settings.MEDIA_ROOT) / mcap_log.original_uri
                
                if not file_path or not file_path.exists():
                    conversion_errors.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - MCAP file not found")
                    print(
                        f"[download] log id={mcap_log.id} skipped: MCAP file not found"
                    )
                    continue
                
                file_path = file_path.resolve()
                print(
                    f"[download] log id={mcap_log.id} resolved path={file_path}, starting conversion"
                )
                
                # Create output directory for converted files
                converted_dir = Path(settings.MEDIA_ROOT) / 'converted'
                converted_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate output filename
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                format_suffix = format.replace('csv_', '') if format.startswith('csv_') else format
                file_extension = 'ld' if format_suffix == 'ld' else 'csv'
                output_filename = f"{mcap_log.id}_{format_suffix}_{timestamp}.{file_extension}"
                output_path = converted_dir / output_filename
                
                # Convert MCAP to CSV/LD synchronously
                converter = McapToCsvConverter()
                converter.convert_to_csv(str(file_path), str(output_path), format=format_suffix)
                
                # Return the path relative to MEDIA_ROOT
                relative_path = output_path.relative_to(settings.MEDIA_ROOT)
                conversion_results[mcap_log] = str(relative_path)
                print(
                    f"[download] log id={mcap_log.id} converted successfully -> {output_path}"
                )
                
            except Exception as e:
                conversion_errors.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - conversion error: {str(e)}")
                print(
                    f"[download] log id={mcap_log.id} conversion error: {e}"
                )
        
        print(
            f"[download] conversions done: succeeded={len(conversion_results)}, failed={len(conversion_errors)}"
        )
        if not conversion_results:
            return Response(
                {
                    'error': 'No files could be converted',
                    'conversion_errors': conversion_errors
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create ZIP file with converted CSV files
        print("[download] creating ZIP archive")
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_file_path = temp_file.name
        temp_file.close()
        
        files_added = 0
        files_missing = []
        
        try:
            with zipfile.ZipFile(temp_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for mcap_log, converted_relative_path in conversion_results.items():
                    try:
                        converted_path = Path(settings.MEDIA_ROOT) / converted_relative_path
                        
                        if not converted_path.exists():
                            files_missing.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - converted file not found at {converted_path}")
                            continue
                        
                        # Generate output filename based on format
                        base_name = Path(mcap_log.file_name).stem
                        format_suffix = format.replace('csv_', '') if format.startswith('csv_') else format
                        file_extension = 'ld' if format_suffix == 'ld' else 'csv'
                        output_filename = f"{base_name}_{format_suffix}.{file_extension}"
                        
                        zip_file.write(str(converted_path), arcname=output_filename)
                        files_added += 1
                    except Exception as file_error:
                        files_missing.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - error: {str(file_error)}")
                        continue
            
            print(f"[download] ZIP written: files_added={files_added}")
            if files_added == 0:
                os.unlink(temp_file_path)
                return Response(
                    {
                        'error': 'No converted files could be added to ZIP',
                        'missing_files': files_missing,
                        'conversion_errors': conversion_errors
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Generate download filename
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            format_display = format.replace('csv_', '') if format.startswith('csv_') else format
            zip_filename = f'mcap_logs_{format_display}_{timestamp}.zip'
            
            # Read ZIP content
            with open(temp_file_path, 'rb') as zip_file:
                zip_content = zip_file.read()
            
            os.unlink(temp_file_path)
            
            print(
                f"[download] sending response: filename={zip_filename}, size={len(zip_content)} bytes"
            )
            # Create response
            response = HttpResponse(zip_content, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
            response['Content-Length'] = len(zip_content)
            
            if files_missing or conversion_errors:
                error_info = []
                if files_missing:
                    error_info.extend(files_missing)
                if conversion_errors:
                    error_info.extend(conversion_errors)
                response['X-Missing-Files'] = ', '.join(error_info)
            
            return response
            
        except Exception as e:
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            
            import traceback
            error_details = traceback.format_exc()
            print(f"CSV download error: {str(e)}\n{error_details}")
            
            return Response(
                {'error': f'Failed to create {format.upper()} ZIP archive: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _download_as_mcap(self, mcap_logs):
        """
        Download original MCAP files as ZIP (original behavior).
        """
        # Create a temporary file for the ZIP
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_file_path = temp_file.name
        temp_file.close()
        
        files_added = 0
        files_missing = []
        
        try:
            # Create ZIP file
            with zipfile.ZipFile(temp_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for mcap_log in mcap_logs:
                    try:
                        if not mcap_log.original_uri:
                            files_missing.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - no file URI")
                            continue
                        
                        # Extract file path from original_uri
                        # original_uri format: /media/mcap_logs/filename.mcap
                        if mcap_log.original_uri.startswith(settings.MEDIA_URL):
                            file_name = mcap_log.original_uri.replace(settings.MEDIA_URL, '', 1)  # Only replace first occurrence
                            file_path = Path(settings.MEDIA_ROOT) / file_name
                        elif mcap_log.original_uri.startswith('/'):
                            # Handle absolute paths starting with /
                            file_path = Path(mcap_log.original_uri)
                        else:
                            # Handle relative paths or other formats
                            file_path = Path(settings.MEDIA_ROOT) / mcap_log.original_uri
                        
                        # Resolve the path to handle any symlinks or relative paths
                        file_path = file_path.resolve()
                        
                        # Check if file exists
                        if not file_path.exists():
                            files_missing.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - file not found at {file_path}")
                            continue
                        
                        # Check if it's actually a file (not a directory)
                        if not file_path.is_file():
                            files_missing.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - path is not a file")
                            continue
                        
                        # Add file to ZIP with original filename
                        zip_file.write(str(file_path), arcname=mcap_log.file_name)
                        files_added += 1
                    except Exception as file_error:
                        # Handle individual file errors gracefully
                        files_missing.append(f"{mcap_log.file_name} (ID: {mcap_log.id}) - error: {str(file_error)}")
                        continue
            
            # If no files were added, return error
            if files_added == 0:
                os.unlink(temp_file_path)
                return Response(
                    {
                        'error': 'No files could be added to the ZIP archive',
                        'missing_files': files_missing
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Generate download filename
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f'mcap_logs_{timestamp}.zip'
            
            # Read the ZIP file into memory for response
            # This ensures proper cleanup of the temp file
            with open(temp_file_path, 'rb') as zip_file:
                zip_content = zip_file.read()
            
            # Delete temp file now that we have the content
            os.unlink(temp_file_path)
            
            # Create response with the ZIP content
            response = HttpResponse(zip_content, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
            response['Content-Length'] = len(zip_content)
            
            # Add info about missing files in response headers if any
            if files_missing:
                response['X-Missing-Files'] = ', '.join(files_missing)
            
            return response
            
        except Exception as e:
            # Clean up temp file on error
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            
            # Log the full error for debugging
            import traceback
            error_details = traceback.format_exc()
            print(f"Download error: {str(e)}\n{error_details}")
            
            return Response(
                {'error': f'Failed to create ZIP archive: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='job-status')
    def job_status(self, request, pk=None):
        """
        Get the parsing job status for a specific MCAP log.
        Returns both the database parse_status and Celery task status.
        """
        mcap_log = self.get_object()
        
        response_data = {
            'log_id': mcap_log.id,
            'file_name': mcap_log.file_name,
            'parse_status': mcap_log.parse_status,
            'parse_task_id': mcap_log.parse_task_id,
        }
        
        # If there's a task ID, get detailed Celery task status
        if mcap_log.parse_task_id:
            try:
                task_result = AsyncResult(mcap_log.parse_task_id)
                response_data['task_state'] = task_result.state
                response_data['task_info'] = {
                    'ready': task_result.ready(),
                    'successful': task_result.successful() if task_result.ready() else None,
                    'failed': task_result.failed() if task_result.ready() else None,
                }
                
                # Add result or error if available
                if task_result.ready():
                    if task_result.successful():
                        response_data['task_info']['result'] = task_result.result
                    elif task_result.failed():
                        response_data['task_info']['error'] = str(task_result.info)
            except Exception as e:
                response_data['task_info'] = {'error': f'Could not fetch task status: {str(e)}'}
        else:
            response_data['task_state'] = None
            response_data['task_info'] = {'message': 'No task ID available'}
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='batch-upload')
    def batch_upload(self, request):
        """
        Upload multiple MCAP files at once.
        Each file will create a database record and trigger a background parsing job.
        Returns a list of created records with their job statuses.
        """
        # Get all uploaded files
        uploaded_files = request.FILES.getlist('files')
        
        if not uploaded_files:
            return Response(
                {'error': 'No files provided. Use multipart/form-data with "files" field containing one or more files.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        media_dir = settings.MEDIA_ROOT / 'mcap_logs'
        media_dir.mkdir(parents=True, exist_ok=True)
        
        for uploaded_file in uploaded_files:
            try:
                # Generate unique filename
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                file_name = f"{timestamp}_{uploaded_file.name}"
                file_path = media_dir / file_name
                
                # Save the uploaded file
                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
                
                saved_file_relpath = str(file_path.relative_to(settings.MEDIA_ROOT))
                
                # Calculate file size
                file_size = file_path.stat().st_size
                
                # Create database record
                mcap_log = McapLog.objects.create(
                    file_name=uploaded_file.name,
                    original_uri=f"{settings.MEDIA_URL}mcap_logs/{file_name}",
                    file_size=file_size,
                    parse_status="pending",
                    recovery_status="pending",
                )
                
                # Trigger recovery (which will trigger parsing when done)
                recovery_task = recover_mcap_file.delay(mcap_log.id, saved_file_relpath)
                mcap_log.parse_task_id = recovery_task.id
                mcap_log.save(update_fields=['parse_task_id'])
                
                # Serialize the result
                serializer = self.get_serializer(mcap_log)
                results.append(serializer.data)
                
            except Exception as e:
                # If one file fails, continue with others
                results.append({
                    'file_name': uploaded_file.name if uploaded_file else 'unknown',
                    'error': str(e),
                    'parse_status': 'error'
                })
        
        return Response({
            'count': len(results),
            'results': results
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'], url_path='job-statuses')
    def job_statuses(self, request):
        """
        Get parsing job statuses for all MCAP logs.
        Optionally filter by parse_status query parameter.
        """
        queryset = McapLog.objects.all()
        
        # Filter by status if provided
        status_filter = request.query_params.get('status', None)
        if status_filter:
            if status_filter.startswith('error'):
                # Match any error status
                queryset = queryset.filter(parse_status__startswith='error')
            else:
                queryset = queryset.filter(parse_status=status_filter)
        
        # Order by created_at descending (newest first)
        queryset = queryset.order_by('-created_at')
        
        # Build response with job statuses
        results = []
        for mcap_log in queryset:
            try:
                job_data = {
                    'log_id': mcap_log.id,
                    'file_name': mcap_log.file_name,
                    'parse_status': mcap_log.parse_status,
                    'parse_task_id': mcap_log.parse_task_id,
                    'created_at': mcap_log.created_at.isoformat() if mcap_log.created_at else None,
                }
                
                # Get Celery task status if task ID exists
                if mcap_log.parse_task_id:
                    try:
                        task_result = AsyncResult(mcap_log.parse_task_id)
                        job_data['task_state'] = task_result.state
                        job_data['task_ready'] = task_result.ready()
                    except Exception as e:
                        # If we can't get task status, still include the record
                        job_data['task_state'] = 'UNKNOWN'
                        job_data['task_error'] = str(e)
                else:
                    job_data['task_state'] = None
                
                results.append(job_data)
            except Exception as e:
                # If there's an error processing a single record, log it but continue
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error processing log {mcap_log.id}: {str(e)}")
                # Still add a basic record
                results.append({
                    'log_id': mcap_log.id,
                    'file_name': getattr(mcap_log, 'file_name', 'unknown'),
                    'parse_status': getattr(mcap_log, 'parse_status', 'unknown'),
                    'error': str(e)
                })
        
        return Response({
            'count': len(results),
            'results': results
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='tag-names')
    def tag_names(self, request):
        """
        Return distinct user-defined tag values across all logs (for filter dropdown).
        """
        seen = set()
        for tags_list in McapLog.objects.exclude(tags=[]).values_list('tags', flat=True):
            if tags_list:
                for t in tags_list:
                    if isinstance(t, str) and t.strip():
                        seen.add(t.strip())
        return Response(sorted(seen))

    @action(detail=False, methods=['get'], url_path='channel-names')
    def channel_names(self, request):
        """
        Return distinct channel names across all logs (for filter dropdown).
        """
        seen = set()
        for ch_list in McapLog.objects.exclude(channels=[]).values_list('channels', flat=True):
            if ch_list:
                for c in ch_list:
                    if isinstance(c, str) and c.strip():
                        seen.add(c.strip())
        return Response(sorted(seen))


class ParseSummaryView(APIView):
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
