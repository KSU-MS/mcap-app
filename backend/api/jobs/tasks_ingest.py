import datetime
import os
import shutil
import subprocess
from pathlib import Path

from celery import shared_task
from celery.signals import worker_ready
from django.conf import settings
from django.contrib.gis.geos import LineString
from django.utils import timezone

from ..gpsparse import GpsParser
from ..map_preview import generate_map_preview_svg
from ..models import McapLog
from ..parser import Parser
from .common import (
    is_non_retryable_recover_error,
    resolve_original_file_for_log,
    resolve_source_file_for_log,
    task_path_value,
)
from .tasks_status import cache_mcap_status


def reenqueue_incomplete_mcap_logs() -> dict[str, int]:
    summary = {
        "queued_recover": 0,
        "queued_parse": 0,
        "skipped_missing_recover_source": 0,
        "skipped_missing_parse_source": 0,
    }

    recover_candidates = McapLog.objects.filter(
        recovery_status__in=["pending", "processing"]
    ).only("id", "original_uri")
    for mcap_log in recover_candidates.iterator(chunk_size=200):
        original_source = resolve_original_file_for_log(mcap_log)
        if not original_source.exists():
            summary["skipped_missing_recover_source"] += 1
            continue

        recover_mcap_file.delay(mcap_log.id, task_path_value(original_source))
        summary["queued_recover"] += 1

    parse_candidates = McapLog.objects.filter(
        recovery_status="completed", parse_status__in=["pending", "processing"]
    ).only("id", "original_uri", "recovered_uri")
    for mcap_log in parse_candidates.iterator(chunk_size=200):
        source_path = resolve_source_file_for_log(mcap_log)
        if not source_path.exists():
            summary["skipped_missing_parse_source"] += 1
            continue

        parse_mcap_file.delay(mcap_log.id, task_path_value(source_path))
        summary["queued_parse"] += 1

    print(f"[startup_reenqueue] {summary}")
    return summary


@worker_ready.connect
def _on_celery_worker_ready(sender=None, **kwargs):
    enabled = os.getenv("MCAP_REQUEUE_ON_CELERY_STARTUP", "1").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        print("[startup_reenqueue] skipped (MCAP_REQUEUE_ON_CELERY_STARTUP disabled)")
        return

    try:
        reenqueue_incomplete_mcap_logs()
    except Exception as exc:
        print(f"[startup_reenqueue] failed: {exc}")


@shared_task(name="api.tasks.recover_mcap_file", bind=True, max_retries=3)
def recover_mcap_file(self, mcap_log_id, file_path):
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)

        p = Path(file_path)
        if not p.is_absolute():
            p = (Path(settings.MEDIA_ROOT) / p).resolve()
        original_file_path = p

        print(
            f"[recover_mcap_file] mcap_log_id={mcap_log_id} "
            f"input_file_path={original_file_path} exists={original_file_path.exists()} "
            f"MEDIA_ROOT={settings.MEDIA_ROOT}"
        )

        if not original_file_path.exists():
            raise FileNotFoundError(f"MCAP file not found: {original_file_path}")

        mcap_log.recovery_status = "processing"
        mcap_log.save(update_fields=["recovery_status"])
        cache_mcap_status(mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status)

        mcap_cmd = shutil.which("mcap")
        if not mcap_cmd:
            raise RuntimeError(
                "mcap command not found in PATH. Please install mcap CLI."
            )

        recovered_dir = Path(settings.MCAP_LOGS_DIR) / "recovered"
        recovered_dir.mkdir(parents=True, exist_ok=True)

        recovered_file_name = (
            f"{original_file_path.stem}-recovered{original_file_path.suffix}"
        )
        recovered_file_path = recovered_dir / recovered_file_name

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
            timeout=300,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise RuntimeError(f"mcap recover failed: {error_msg}")

        if not recovered_file_path.exists():
            raise FileNotFoundError(
                f"Recovered file was not created: {recovered_file_path}"
            )

        recovery_output = ""
        if result.stdout and result.stdout.strip():
            recovery_output = result.stdout.strip()
        elif result.stderr and result.stderr.strip():
            recovery_output = result.stderr.strip()

        if recovery_output:
            print(f"[recover_mcap_file] Recovery statistics: {recovery_output}")

        recovered_relpath = recovered_file_path.relative_to(settings.MEDIA_ROOT)
        mcap_log.recovered_uri = f"{settings.MEDIA_URL}{recovered_relpath.as_posix()}"
        mcap_log.recovery_status = "completed"
        mcap_log.save(update_fields=["recovered_uri", "recovery_status"])
        cache_mcap_status(mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status)

        print(
            f"[recover_mcap_file] Successfully recovered MCAP file: {recovered_file_path}"
        )

        parse_mcap_file.delay(mcap_log_id, file_path)
        return mcap_log_id

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except subprocess.TimeoutExpired:
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.recovery_status = "error: timeout after 5 minutes"
            mcap_log.save(update_fields=["recovery_status"])
            cache_mcap_status(
                mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status
            )
        except Exception:
            pass
        return f"Recovery timed out for log {mcap_log_id}"
    except Exception as e:
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.recovery_status = f"error: {str(e)}"
            mcap_log.save(update_fields=["recovery_status"])
            cache_mcap_status(
                mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status
            )
        except Exception:
            pass

        if (
            not is_non_retryable_recover_error(e)
            and self.request.retries < self.max_retries
        ):
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error recovering MCAP file: {str(e)}"


@shared_task(name="api.tasks.parse_mcap_file", bind=True, max_retries=3)
def parse_mcap_file(self, mcap_log_id, file_path):
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)
        source_path = resolve_source_file_for_log(mcap_log, file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"MCAP file not found for parsing: {source_path}")

        mcap_log.parse_status = "processing"
        mcap_log.save(update_fields=["parse_status"])
        cache_mcap_status(mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status)

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
        cache_mcap_status(mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status)

        extract_gps_path.delay(mcap_log_id, str(source_path))
        return f"Successfully parsed metadata for log {mcap_log_id}"

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        try:
            mcap_log = McapLog.objects.get(id=mcap_log_id)
            mcap_log.parse_status = f"error: {str(e)}"
            mcap_log.gps_status = "skipped"
            mcap_log.map_preview_status = "skipped"
            mcap_log.save(
                update_fields=["parse_status", "gps_status", "map_preview_status"]
            )
            cache_mcap_status(
                mcap_log.id, mcap_log.recovery_status, mcap_log.parse_status
            )
        except Exception:
            pass

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error parsing MCAP file: {str(e)}"


@shared_task(name="api.tasks.extract_gps_path", bind=True, max_retries=3)
def extract_gps_path(self, mcap_log_id, file_path):
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)
        source_path = resolve_source_file_for_log(mcap_log, file_path)
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


@shared_task(name="api.tasks.generate_map_preview", bind=True, max_retries=2)
def generate_map_preview(self, mcap_log_id):
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)
        mcap_log.map_preview_status = "processing"
        mcap_log.map_preview_error = None
        mcap_log.save(update_fields=["map_preview_status", "map_preview_error"])

        if mcap_log.map_preview_uri:
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
