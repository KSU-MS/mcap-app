"""Backward-compatible task module for DB-backed background jobs."""

from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from .models import BackgroundJob, ExportJob, McapLog
from .services.contracts import ExportProgressSnapshot
from .services.background_jobs import (
    enqueue_export_job,
    enqueue_ingest_job,
    enqueue_map_preview_job,
)


def resolve_source_file_for_log(mcap_log: McapLog, file_path: str | None = None) -> Path:
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


def resolve_original_file_for_log(mcap_log: McapLog) -> Path:
    original_uri = str(mcap_log.original_uri or "")
    if not original_uri:
        return Path("")

    if original_uri.startswith(settings.MEDIA_URL):
        rel = original_uri.replace(settings.MEDIA_URL, "", 1)
        return Path(settings.MEDIA_ROOT) / rel
    if original_uri.startswith("/"):
        return Path(original_uri)
    return Path(settings.MEDIA_ROOT) / original_uri


def is_non_retryable_recover_error(exc: Exception) -> bool:
    message = str(exc).lower()
    non_retryable_markers = (
        "invalid zero opcode",
        "invalid magic at start of file",
        "not a valid mcap",
        "file is too small",
        "no such file or directory",
        "mcap file not found",
    )
    return any(marker in message for marker in non_retryable_markers)


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


def recover_mcap_file(mcap_log_id: int, file_path: str):
    return enqueue_ingest_job(mcap_log_id, file_path)


def parse_mcap_file(mcap_log_id: int, file_path: str):
    return enqueue_ingest_job(mcap_log_id, file_path)


def extract_gps_path(mcap_log_id: int, file_path: str):
    return enqueue_ingest_job(mcap_log_id, file_path)


def generate_map_preview(mcap_log_id: int):
    return enqueue_map_preview_job(mcap_log_id)


def reenqueue_incomplete_mcap_logs() -> dict[str, int]:
    summary = {
        "queued_ingest": 0,
        "queued_export": 0,
        "skipped_missing_source": 0,
    }

    ingest_candidates = McapLog.objects.filter(
        Q(recovery_status__in=["pending", "processing"])
        | Q(parse_status__in=["pending", "processing"])
    ).only("id", "original_uri", "recovered_uri")

    for mcap_log in ingest_candidates.iterator(chunk_size=200):
        source = resolve_source_file_for_log(mcap_log)
        if not source.exists():
            source = resolve_original_file_for_log(mcap_log)
        if not source.exists():
            summary["skipped_missing_source"] += 1
            continue

        try:
            rel = str(source.resolve().relative_to(settings.MEDIA_ROOT))
        except Exception:
            rel = str(source)

        enqueue_ingest_job(mcap_log.id, rel)
        summary["queued_ingest"] += 1

    active_exports = ExportJob.objects.filter(
        status__in=["pending", "processing"]
    ).only("id")
    for export_job in active_exports.iterator(chunk_size=200):
        enqueue_export_job(export_job.id)
        summary["queued_export"] += 1

    return summary


def convert_export_item(*args, **kwargs):  # pragma: no cover
    raise RuntimeError(
        "convert_export_item is Celery-only and has been removed. "
        "Use enqueue_export_job instead."
    )


def finalize_export_job(*args, **kwargs):  # pragma: no cover
    raise RuntimeError(
        "finalize_export_job is Celery-only and has been removed. "
        "Use enqueue_export_job instead."
    )


def convert_mcap_to_csv(*args, **kwargs):  # pragma: no cover
    raise RuntimeError(
        "convert_mcap_to_csv task is Celery-only and has been removed. "
        "Use export job endpoints instead."
    )


__all__ = [
    "recover_mcap_file",
    "parse_mcap_file",
    "extract_gps_path",
    "generate_map_preview",
    "reenqueue_incomplete_mcap_logs",
    "enqueue_export_job",
    "enqueue_ingest_job",
    "enqueue_map_preview_job",
    "cache_mcap_status",
    "cache_export_status",
    "BackgroundJob",
]
