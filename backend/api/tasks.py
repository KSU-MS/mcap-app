"""
Background tasks for MCAP log processing.
"""

from celery import shared_task
from django.contrib.gis.geos import LineString
from django.utils import timezone
from django.conf import settings
from pathlib import Path
import datetime
import subprocess
import shutil
from .models import McapLog
from .parser import Parser
from .gpsparse import GpsParser
from .mcap_converter import McapToCsvConverter
from .map_preview import generate_map_preview_svg


@shared_task(bind=True, max_retries=3)
def recover_mcap_file(self, mcap_log_id, file_path):
    """
    Background task to recover an MCAP file using 'mcap recover' command.

    Args:
        mcap_log_id: The ID of the McapLog record to update
        file_path: Relative path (preferred) or absolute path to the MCAP file to recover
    """
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)

        # Resolve relative paths against MEDIA_ROOT to support Dockerized workers
        p = Path(file_path)
        if not p.is_absolute():
            p = (Path(settings.MEDIA_ROOT) / p).resolve()
        original_file_path = p

        # Helpful debug
        print(
            f"[recover_mcap_file] mcap_log_id={mcap_log_id} "
            f"input_file_path={original_file_path} exists={original_file_path.exists()} "
            f"MEDIA_ROOT={settings.MEDIA_ROOT}"
        )

        if not original_file_path.exists():
            raise FileNotFoundError(f"MCAP file not found: {original_file_path}")

        # Update recovery status to processing
        mcap_log.recovery_status = "processing"
        mcap_log.save(update_fields=["recovery_status"])

        # Find mcap command
        mcap_cmd = shutil.which("mcap")
        if not mcap_cmd:
            raise RuntimeError(
                "mcap command not found in PATH. Please install mcap CLI."
            )

        # Create recovered directory inside mcap_logs folder
        recovered_dir = Path(settings.MEDIA_ROOT) / "mcap_logs" / "recovered"
        recovered_dir.mkdir(parents=True, exist_ok=True)

        # Create recovered file path with descriptive naming (original filename + recovery suffix)
        recovered_file_name = (
            f"{original_file_path.stem}-recovered{original_file_path.suffix}"
        )
        recovered_file_path = recovered_dir / recovered_file_name

        # Run mcap recover command with -o flag
        # mcap recover input.mcap -o output.mcap
        result = subprocess.run(
            [
                mcap_cmd,
                "recover",
                str(original_file_path),
                "-o",
                str(recovered_file_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise RuntimeError(f"mcap recover failed: {error_msg}")

        # Check if recovered file was created
        if not recovered_file_path.exists():
            raise FileNotFoundError(
                f"Recovered file was not created: {recovered_file_path}"
            )

        # Log recovery statistics from stdout or stderr (e.g., "Recovered 3728056 messages, 0 attachments, and 0 metadata records.")
        # The mcap CLI may output to either stdout or stderr
        recovery_output = ""
        if result.stdout and result.stdout.strip():
            recovery_output = result.stdout.strip()
        elif result.stderr and result.stderr.strip():
            # Sometimes output goes to stderr even on success
            recovery_output = result.stderr.strip()

        if recovery_output:
            print(f"[recover_mcap_file] Recovery statistics: {recovery_output}")

        # Store the recovered file URI (relative to MEDIA_ROOT)
        recovered_relpath = recovered_file_path.relative_to(settings.MEDIA_ROOT)
        mcap_log.recovered_uri = f"{settings.MEDIA_URL}{recovered_relpath.as_posix()}"
        mcap_log.recovery_status = "completed"
        mcap_log.save(update_fields=["recovered_uri", "recovery_status"])

        print(
            f"[recover_mcap_file] Successfully recovered MCAP file: {recovered_file_path}"
        )

        # Trigger parsing after recovery completes
        # Use the original file_path (relative) - parse will use recovered file if available
        parse_mcap_file.delay(mcap_log_id, file_path)

        return mcap_log_id  # Return ID for potential chaining

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except subprocess.TimeoutExpired:
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.recovery_status = "error: timeout after 5 minutes"
            mcap_log.save(update_fields=["recovery_status"])
        except:
            pass
        return f"Recovery timed out for log {mcap_log_id}"
    except Exception as e:
        # Update recovery status with error
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.recovery_status = f"error: {str(e)}"
            mcap_log.save(update_fields=["recovery_status"])
        except:
            pass

        # Retry the task if it's a retryable error
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error recovering MCAP file: {str(e)}"


@shared_task(bind=True, max_retries=3)
def parse_mcap_file(self, mcap_log_id, file_path):
    """
    Background task to parse an MCAP file and update the database record.

    Args:
        mcap_log_id: The ID of the McapLog record to update
        file_path: Relative path (preferred) or absolute path to the MCAP file to parse
    """
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)

        # Resolve relative paths against MEDIA_ROOT to support Dockerized workers
        p = Path(file_path)
        if not p.is_absolute():
            p = (Path(settings.MEDIA_ROOT) / p).resolve()
        original_file_path = p

        # Try to use recovered file if available, otherwise use original
        file_to_parse = None
        if mcap_log.recovered_uri and mcap_log.recovered_uri != "pending":
            # Extract path from recovered_uri
            if mcap_log.recovered_uri.startswith(settings.MEDIA_URL):
                file_name = mcap_log.recovered_uri.replace(settings.MEDIA_URL, "", 1)
                recovered_path = Path(settings.MEDIA_ROOT) / file_name
            elif mcap_log.recovered_uri.startswith("/"):
                recovered_path = Path(mcap_log.recovered_uri)
            else:
                recovered_path = Path(settings.MEDIA_ROOT) / mcap_log.recovered_uri

            if recovered_path.exists():
                file_to_parse = str(recovered_path)
                print(f"[parse_mcap_file] Using recovered file: {file_to_parse}")

        # Fall back to original file if recovered file not available
        if not file_to_parse:
            file_to_parse = str(original_file_path)
            print(f"[parse_mcap_file] Using original file: {file_to_parse}")

        # Helpful debug for Docker issues (shows exactly what path Celery is trying to read)
        print(
            f"[parse_mcap_file] mcap_log_id={mcap_log_id} "
            f"input_file_path={file_to_parse} exists={Path(file_to_parse).exists()} "
            f"MEDIA_ROOT={settings.MEDIA_ROOT}"
        )

        if not Path(file_to_parse).exists():
            raise FileNotFoundError(f"MCAP file not found for parsing: {file_to_parse}")

        # Update parse status to processing
        mcap_log.parse_status = "processing"
        mcap_log.save(update_fields=["parse_status"])

        # Parse the MCAP file
        parsed_data = Parser.parse_stuff(file_to_parse)

        # Update fields from parsed data
        mcap_log.channels = parsed_data.get("channels", [])
        mcap_log.channel_count = parsed_data.get("channel_count", 0)
        mcap_log.start_time = parsed_data.get("start_time")
        mcap_log.end_time = parsed_data.get("end_time")
        mcap_log.duration_seconds = parsed_data.get("duration", 0)

        # Parse GPS coordinates from the file
        gps_data = GpsParser.parse_gps(file_to_parse)
        all_coordinates = gps_data.get("all_coordinates", [])

        # Create LineString from GPS coordinates when usable for vector path preview
        if len(all_coordinates) >= 2:
            mcap_log.lap_path = LineString(all_coordinates, srid=4326)
        else:
            mcap_log.lap_path = None
            mcap_log.map_preview_uri = None

        # Set captured_at from start_time
        if parsed_data.get("start_time"):
            naive_dt = datetime.datetime.fromtimestamp(parsed_data.get("start_time"))
            mcap_log.captured_at = timezone.make_aware(naive_dt)

        # Mark as completed
        mcap_log.parse_status = "completed"
        mcap_log.save()

        # Generate immutable preview asynchronously only when GPS path exists
        if mcap_log.lap_path:
            try:
                generate_map_preview.delay(mcap_log_id)
            except Exception as preview_queue_err:
                print(
                    f"[parse_mcap_file] Could not queue map preview for log {mcap_log_id}: {preview_queue_err}"
                )

        return f"Successfully parsed MCAP file for log {mcap_log_id}"

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        # Update parse status with error
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.parse_status = f"error: {str(e)}"
            mcap_log.save(update_fields=["parse_status"])
        except:
            pass

        # Retry the task if it's a retryable error
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error parsing MCAP file: {str(e)}"


@shared_task(bind=True, max_retries=2)
def generate_map_preview(self, mcap_log_id):
    """Generate immutable SVG map preview thumbnail for a log."""
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)

        if mcap_log.map_preview_uri:
            # Immutable preview; skip regeneration once set
            return f"Map preview already exists for log {mcap_log_id}"

        if not mcap_log.lap_path:
            return f"No lap_path available for log {mcap_log_id}"

        coords = []
        for point in list(mcap_log.lap_path.coords):
            if len(point) < 2:
                continue
            lon = float(point[0])
            lat = float(point[1])
            coords.append((lon, lat))

        if not coords:
            return f"No usable coordinates for log {mcap_log_id}"

        _, uri = generate_map_preview_svg(log_id=mcap_log_id, coords=coords)
        mcap_log.map_preview_uri = uri
        mcap_log.save(update_fields=["map_preview_uri"])
        return f"Generated map preview for log {mcap_log_id}"

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))
        return f"Error generating map preview for log {mcap_log_id}: {str(e)}"


@shared_task(bind=True, max_retries=3)
def convert_mcap_to_csv(self, mcap_log_id, format="omni"):
    """
    Background task to convert an MCAP file to CSV/LD format.

    Args:
        mcap_log_id: The ID of the McapLog record to convert
        format: Format profile ('omni', 'tvn', or 'ld')

    Returns:
        Path to the converted file
    """
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)

        # Determine source file path
        file_path = None

        # Try recovered_uri first if available and not pending
        if mcap_log.recovered_uri and mcap_log.recovered_uri != "pending":
            if mcap_log.recovered_uri.startswith(settings.MEDIA_URL):
                file_name = mcap_log.recovered_uri.replace(settings.MEDIA_URL, "", 1)
                file_path = Path(settings.MEDIA_ROOT) / file_name
            elif mcap_log.recovered_uri.startswith("/"):
                file_path = Path(mcap_log.recovered_uri)
            else:
                file_path = Path(settings.MEDIA_ROOT) / mcap_log.recovered_uri

        # Fall back to original_uri if recovered_uri not available
        if not file_path or not file_path.exists():
            if mcap_log.original_uri:
                if mcap_log.original_uri.startswith(settings.MEDIA_URL):
                    file_name = mcap_log.original_uri.replace(settings.MEDIA_URL, "", 1)
                    file_path = Path(settings.MEDIA_ROOT) / file_name
                elif mcap_log.original_uri.startswith("/"):
                    file_path = Path(mcap_log.original_uri)
                else:
                    file_path = Path(settings.MEDIA_ROOT) / mcap_log.original_uri

        if not file_path or not file_path.exists():
            raise FileNotFoundError(f"MCAP file not found for log {mcap_log_id}")

        file_path = file_path.resolve()

        # Create output directory for converted files
        converted_dir = Path(settings.MEDIA_ROOT) / "converted"
        converted_dir.mkdir(parents=True, exist_ok=True)

        # Generate output filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        format_suffix = (
            format.replace("csv_", "") if format.startswith("csv_") else format
        )
        # Use appropriate file extension based on format
        file_extension = "ld" if format_suffix == "ld" else "csv"
        output_filename = f"{mcap_log_id}_{format_suffix}_{timestamp}.{file_extension}"
        output_path = converted_dir / output_filename

        # Convert MCAP to CSV/LD
        converter = McapToCsvConverter()
        converter.convert_to_csv(str(file_path), str(output_path), format=format_suffix)

        # Return the path relative to MEDIA_ROOT for easy access
        relative_path = output_path.relative_to(settings.MEDIA_ROOT)
        return str(relative_path)

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        # Retry the task if it's a retryable error
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error converting MCAP file to {format}: {str(e)}"
