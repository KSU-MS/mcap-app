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
import zipfile
from celery import chord
from .models import McapLog, ExportJob, ExportItem
from .parser import Parser
from .gpsparse import GpsParser
from .mcap_converter import McapToCsvConverter
from .map_preview import generate_map_preview_svg


def _resolve_source_file_for_log(
    mcap_log: McapLog, file_path: str | None = None
) -> Path:
    original_file_path = None
    original_uri = str(mcap_log.original_uri or "")
    recovered_uri = str(mcap_log.recovered_uri or "")
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = (Path(settings.MEDIA_ROOT) / p).resolve()
        original_file_path = p

    if not original_file_path and original_uri:
        if original_uri.startswith(settings.MEDIA_URL):
            rel = original_uri.replace(settings.MEDIA_URL, "", 1)
            original_file_path = Path(settings.MEDIA_ROOT) / rel
        elif original_uri.startswith("/"):
            original_file_path = Path(original_uri)
        else:
            original_file_path = Path(settings.MEDIA_ROOT) / original_uri

    if recovered_uri and recovered_uri != "pending":
        if recovered_uri.startswith(settings.MEDIA_URL):
            rel = recovered_uri.replace(settings.MEDIA_URL, "", 1)
            recovered_path = Path(settings.MEDIA_ROOT) / rel
        elif recovered_uri.startswith("/"):
            recovered_path = Path(recovered_uri)
        else:
            recovered_path = Path(settings.MEDIA_ROOT) / recovered_uri
        if recovered_path.exists():
            return recovered_path

    return original_file_path or Path("")


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
        source_path = _resolve_source_file_for_log(mcap_log, file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"MCAP file not found for parsing: {source_path}")

        mcap_log.parse_status = "processing"
        mcap_log.save(update_fields=["parse_status"])

        parsed_data = Parser.parse_stuff(str(source_path))
        mcap_log.channels = parsed_data.get("channels", [])
        mcap_log.channel_count = parsed_data.get("channel_count", 0)
        mcap_log.start_time = parsed_data.get("start_time")
        mcap_log.end_time = parsed_data.get("end_time")
        mcap_log.duration_seconds = parsed_data.get("duration", 0)
        if parsed_data.get("start_time"):
            naive_dt = datetime.datetime.fromtimestamp(parsed_data.get("start_time"))
            mcap_log.captured_at = timezone.make_aware(naive_dt)

        mcap_log.parse_status = "completed"
        mcap_log.gps_status = "pending"
        mcap_log.gps_error = None
        mcap_log.map_preview_status = "pending"
        mcap_log.map_preview_error = None
        mcap_log.save()

        extract_gps_path.delay(mcap_log_id, str(source_path))
        return f"Successfully parsed metadata for log {mcap_log_id}"

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        # Update parse status with error
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.parse_status = f"error: {str(e)}"
            mcap_log.gps_status = "skipped"
            mcap_log.map_preview_status = "skipped"
            mcap_log.save(
                update_fields=["parse_status", "gps_status", "map_preview_status"]
            )
        except:
            pass

        # Retry the task if it's a retryable error
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error parsing MCAP file: {str(e)}"


@shared_task(bind=True, max_retries=3)
def extract_gps_path(self, mcap_log_id, file_path):
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)
        source_path = _resolve_source_file_for_log(mcap_log, file_path)
        if not source_path.exists():
            raise FileNotFoundError(
                f"MCAP file not found for GPS extraction: {source_path}"
            )

        mcap_log.gps_status = "processing"
        mcap_log.gps_error = None
        mcap_log.save(update_fields=["gps_status", "gps_error"])

        gps_data = GpsParser.parse_gps(str(source_path))
        all_coordinates = gps_data.get("all_coordinates", [])

        if len(all_coordinates) >= 2:
            mcap_log.lap_path = LineString(all_coordinates, srid=4326)
            mcap_log.gps_status = "completed"
            mcap_log.map_preview_status = "pending"
            mcap_log.save(
                update_fields=["lap_path", "gps_status", "map_preview_status"]
            )
            generate_map_preview.delay(mcap_log_id)
            return f"Extracted GPS path for log {mcap_log_id}"

        mcap_log.lap_path = None
        mcap_log.map_preview_uri = None
        mcap_log.gps_status = "completed"
        mcap_log.map_preview_status = "skipped"
        mcap_log.save(
            update_fields=[
                "lap_path",
                "map_preview_uri",
                "gps_status",
                "map_preview_status",
            ]
        )
        return f"No GPS path available for log {mcap_log_id}"
    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.gps_status = "failed"
            mcap_log.gps_error = str(e)
            mcap_log.map_preview_status = "skipped"
            mcap_log.save(
                update_fields=["gps_status", "gps_error", "map_preview_status"]
            )
        except Exception:
            pass
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return f"Error extracting GPS path for log {mcap_log_id}: {str(e)}"


@shared_task(bind=True, max_retries=2)
def generate_map_preview(self, mcap_log_id):
    """Generate immutable SVG map preview thumbnail for a log."""
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)
        mcap_log.map_preview_status = "processing"
        mcap_log.map_preview_error = None
        mcap_log.save(update_fields=["map_preview_status", "map_preview_error"])

        if mcap_log.map_preview_uri:
            # Immutable preview; skip regeneration once set
            mcap_log.map_preview_status = "completed"
            mcap_log.save(update_fields=["map_preview_status"])
            return f"Map preview already exists for log {mcap_log_id}"

        if not mcap_log.lap_path:
            mcap_log.map_preview_status = "skipped"
            mcap_log.save(update_fields=["map_preview_status"])
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
        mcap_log.map_preview_status = "completed"
        mcap_log.save(update_fields=["map_preview_uri", "map_preview_status"])
        return f"Generated map preview for log {mcap_log_id}"

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.map_preview_status = "failed"
            mcap_log.map_preview_error = str(e)
            mcap_log.save(update_fields=["map_preview_status", "map_preview_error"])
        except Exception:
            pass
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))
        return f"Error generating map preview for log {mcap_log_id}: {str(e)}"


@shared_task(bind=True, max_retries=2)
def convert_export_item(self, export_item_id):
    try:
        item = ExportItem.objects.select_related("job", "mcap_log").get(
            id=export_item_id
        )
        item.status = "processing"
        item.attempts += 1
        item.error_message = None
        item.save(update_fields=["status", "attempts", "error_message", "updated_at"])

        mcap_log = item.mcap_log
        source_path = _resolve_source_file_for_log(mcap_log)
        if not source_path.exists():
            raise FileNotFoundError(f"MCAP source not found: {source_path}")

        format_suffix = (
            item.job.format.replace("csv_", "")
            if item.job.format.startswith("csv_")
            else item.job.format
        )
        file_extension = "ld" if format_suffix == "ld" else "csv"

        export_dir = Path(settings.MEDIA_ROOT) / "exports" / str(item.job_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"{item.mcap_log_id}_{format_suffix}.{file_extension}"
        output_path = export_dir / output_filename

        converter = McapToCsvConverter()
        converter.convert_to_csv(
            str(source_path), str(output_path), format=format_suffix
        )

        relpath = output_path.relative_to(settings.MEDIA_ROOT).as_posix()
        item.output_uri = f"{settings.MEDIA_URL}{relpath}"
        item.status = "completed"
        item.save(update_fields=["output_uri", "status", "updated_at"])
        return {"item_id": export_item_id, "status": "completed"}
    except ExportItem.DoesNotExist:
        return {"item_id": export_item_id, "status": "missing"}
    except Exception as e:
        try:
            item = ExportItem.objects.get(id=export_item_id)
            item.status = "failed"
            item.error_message = str(e)
            item.save(update_fields=["status", "error_message", "updated_at"])
        except Exception:
            pass
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))
        return {"item_id": export_item_id, "status": "failed", "error": str(e)}


@shared_task(bind=True, max_retries=1)
def finalize_export_job(self, results, export_job_id):
    try:
        job = ExportJob.objects.get(id=export_job_id)
        items = list(job.items.select_related("mcap_log"))
        completed = [i for i in items if i.status == "completed" and i.output_uri]
        failed = [i for i in items if i.status == "failed"]

        if not completed:
            job.status = "failed"
            job.error_message = "No files were converted successfully"
            job.completed_at = timezone.now()
            job.save(
                update_fields=["status", "error_message", "completed_at", "updated_at"]
            )
            return f"Export job {export_job_id} failed"

        export_dir = Path(settings.MEDIA_ROOT) / "exports" / str(job.id)
        export_dir.mkdir(parents=True, exist_ok=True)
        zip_path = export_dir / "bundle.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for item in completed:
                if not item.output_uri:
                    continue
                rel = item.output_uri.replace(settings.MEDIA_URL, "", 1)
                abs_path = Path(settings.MEDIA_ROOT) / rel
                if not abs_path.exists():
                    continue
                base_name = Path(item.mcap_log.file_name).stem
                fmt = job.format.replace("csv_", "")
                ext = "ld" if fmt == "ld" else "csv"
                zip_file.write(str(abs_path), arcname=f"{base_name}_{fmt}.{ext}")

        job_rel = zip_path.relative_to(settings.MEDIA_ROOT).as_posix()
        job.zip_uri = f"{settings.MEDIA_URL}{job_rel}"
        job.status = "completed_with_errors" if failed else "completed"
        if failed:
            job.error_message = f"{len(failed)} item(s) failed"
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "zip_uri",
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )
        return f"Export job {export_job_id} finalized"
    except ExportJob.DoesNotExist:
        return f"ExportJob with id {export_job_id} does not exist"
    except Exception as e:
        try:
            job = ExportJob.objects.get(id=export_job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save(
                update_fields=["status", "error_message", "completed_at", "updated_at"]
            )
        except Exception:
            pass
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30)
        return f"Error finalizing export job {export_job_id}: {str(e)}"


def enqueue_export_job(export_job_id):
    job = ExportJob.objects.get(id=export_job_id)
    item_ids = list(job.items.values_list("id", flat=True))
    if not item_ids:
        job.status = "failed"
        job.error_message = "No items found for export job"
        job.completed_at = timezone.now()
        job.save(
            update_fields=["status", "error_message", "completed_at", "updated_at"]
        )
        return

    job.status = "processing"
    job.save(update_fields=["status", "updated_at"])
    header = [convert_export_item.s(item_id) for item_id in item_ids]
    callback = finalize_export_job.s(export_job_id)
    chord(header)(callback)


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
