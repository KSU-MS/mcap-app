import datetime
import zipfile
from pathlib import Path

from celery import chord, shared_task
from django.conf import settings
from django.utils import timezone

from ..models import ExportItem, ExportJob, McapLog
from ..services.contracts import ConversionRequest
from ..services.conversion_service import McapConversionService
from .common import resolve_source_file_for_log
from .tasks_status import cache_export_status


@shared_task(name="api.tasks.convert_export_item", bind=True, max_retries=2)
def convert_export_item(self, export_item_id):
    try:
        item = ExportItem.objects.select_related("job", "mcap_log").get(
            id=export_item_id
        )
        item.status = "processing"
        item.attempts += 1
        item.error_message = None
        item.save(update_fields=["status", "attempts", "error_message", "updated_at"])
        cache_export_status(item.job_id)

        mcap_log = item.mcap_log
        source_path = resolve_source_file_for_log(mcap_log)
        if not source_path.exists():
            raise FileNotFoundError(f"MCAP source not found: {source_path}")

        format_suffix = (
            item.job.format.replace("csv_", "")
            if item.job.format.startswith("csv_")
            else item.job.format
        )
        resample_hz = getattr(
            item.job, "resample_hz", settings.MOTEC_RESAMPLE_HZ_DEFAULT
        )
        file_extension = "ld" if format_suffix == "ld" else "csv"

        export_dir = Path(settings.MEDIA_ROOT) / "exports" / str(item.job_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"{item.mcap_log_id}_{format_suffix}.{file_extension}"
        output_path = export_dir / output_filename

        service = McapConversionService()
        conversion_result = service.convert_with_result(
            ConversionRequest(
                source_path=source_path,
                output_path=output_path,
                format_suffix=format_suffix,
                resample_hz=resample_hz,
            )
        )
        if not conversion_result.success:
            raise RuntimeError(conversion_result.error or "Conversion failed")

        relpath = output_path.relative_to(settings.MEDIA_ROOT).as_posix()
        item.output_uri = f"{settings.MEDIA_URL}{relpath}"
        item.status = "completed"
        item.save(update_fields=["output_uri", "status", "updated_at"])
        cache_export_status(item.job_id)
        return {"item_id": export_item_id, "status": "completed"}
    except ExportItem.DoesNotExist:
        return {"item_id": export_item_id, "status": "missing"}
    except Exception as e:
        try:
            item = ExportItem.objects.get(id=export_item_id)
            item.status = "failed"
            item.error_message = str(e)
            item.save(update_fields=["status", "error_message", "updated_at"])
            cache_export_status(item.job_id)
        except Exception:
            pass
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=30 * (self.request.retries + 1))
        return {"item_id": export_item_id, "status": "failed", "error": str(e)}


@shared_task(name="api.tasks.finalize_export_job", bind=True, max_retries=1)
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
            cache_export_status(job.id)
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
        cache_export_status(job.id)
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
            cache_export_status(job.id)
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
        cache_export_status(job.id)
        return

    job.status = "processing"
    job.save(update_fields=["status", "updated_at"])
    cache_export_status(job.id)
    header = [convert_export_item.s(item_id) for item_id in item_ids]
    callback = finalize_export_job.s(export_job_id)
    chord(header)(callback)


@shared_task(name="api.tasks.convert_mcap_to_csv", bind=True, max_retries=3)
def convert_mcap_to_csv(self, mcap_log_id, format="omni", resample_hz=None):
    try:
        mcap_log = McapLog.objects.get(id=mcap_log_id)

        file_path = resolve_source_file_for_log(mcap_log)
        if not file_path.exists():
            raise FileNotFoundError(f"MCAP file not found for log {mcap_log_id}")

        file_path = file_path.resolve()

        converted_dir = Path(settings.MEDIA_ROOT) / "converted"
        converted_dir.mkdir(parents=True, exist_ok=True)

        if resample_hz is None:
            resample_hz = settings.MOTEC_RESAMPLE_HZ_DEFAULT

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        format_suffix = (
            format.replace("csv_", "") if format.startswith("csv_") else format
        )
        file_extension = "ld" if format_suffix == "ld" else "csv"
        output_filename = f"{mcap_log_id}_{format_suffix}_{timestamp}.{file_extension}"
        output_path = converted_dir / output_filename

        service = McapConversionService()
        conversion_result = service.convert_with_result(
            ConversionRequest(
                source_path=file_path,
                output_path=output_path,
                format_suffix=format_suffix,
                resample_hz=resample_hz,
            )
        )
        if not conversion_result.success:
            raise RuntimeError(conversion_result.error or "Conversion failed")

        relative_path = output_path.relative_to(settings.MEDIA_ROOT)
        return str(relative_path)

    except McapLog.DoesNotExist:
        return f"McapLog with id {mcap_log_id} does not exist"
    except Exception as e:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return f"Error converting MCAP file to {format}: {str(e)}"
