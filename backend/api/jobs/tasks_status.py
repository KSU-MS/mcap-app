from django.core.cache import cache

from ..models import ExportJob
from ..services.contracts import ExportProgressSnapshot


def cache_mcap_status(log_id: int, recovery_status: str, parse_status: str) -> None:
    payload = {
        "recovery_status": recovery_status,
        "parse_status": parse_status,
    }
    recovery_terminal = recovery_status in {
        "completed",
        "success",
    } or recovery_status.startswith("error")
    parse_terminal = parse_status in {
        "completed",
        "success",
    } or parse_status.startswith("error")
    if recovery_terminal and parse_terminal:
        cache.delete(f"mcap_status:{log_id}")
        return
    cache.set(f"mcap_status:{log_id}", payload, timeout=15)


def cache_export_status(job_id: int) -> None:
    try:
        job = ExportJob.objects.prefetch_related("items").get(id=job_id)
    except ExportJob.DoesNotExist:
        cache.delete(f"export_status:{job_id}")
        return

    total_items = job.items.count()
    completed_items = job.items.filter(status="completed").count()
    failed_items = job.items.filter(status="failed").count()
    done_items = completed_items + failed_items
    progress_percent = int((done_items / total_items) * 100) if total_items else 0

    snapshot = ExportProgressSnapshot(
        id=job.id,
        status=job.status,
        format=job.format,
        resample_hz=job.resample_hz,
        error_message=job.error_message,
        total_items=total_items,
        completed_items=completed_items,
        failed_items=failed_items,
        progress_percent=min(100, progress_percent),
    )

    if job.status in {"completed", "completed_with_errors", "failed"}:
        cache.delete(f"export_status:{job_id}")
        return

    cache.set(f"export_status:{job_id}", snapshot.to_payload(), timeout=15)
