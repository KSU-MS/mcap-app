from ..models import BackgroundJob


def enqueue_ingest_job(
    mcap_log_id: int, file_path: str, max_attempts: int = 3
) -> BackgroundJob:
    return BackgroundJob.objects.create(
        job_type=BackgroundJob.Type.INGEST_PIPELINE,
        payload={"mcap_log_id": int(mcap_log_id), "file_path": str(file_path)},
        max_attempts=max_attempts,
    )


def enqueue_export_job(export_job_id: int, max_attempts: int = 2) -> BackgroundJob:
    return BackgroundJob.objects.create(
        job_type=BackgroundJob.Type.EXPORT_JOB,
        payload={"export_job_id": int(export_job_id)},
        max_attempts=max_attempts,
    )


def enqueue_map_preview_job(mcap_log_id: int, max_attempts: int = 2) -> BackgroundJob:
    return BackgroundJob.objects.create(
        job_type=BackgroundJob.Type.MAP_PREVIEW,
        payload={"mcap_log_id": int(mcap_log_id)},
        max_attempts=max_attempts,
    )
