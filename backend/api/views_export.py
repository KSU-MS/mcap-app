from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ExportItem, ExportJob, McapLog
from .serializers import ExportCreateRequestSerializer, ExportJobSerializer
from .tasks import enqueue_export_job


class ExportActionsMixin:
    def _visible_logs_queryset(self, request):
        return McapLog.objects.filter(Q(user=request.user) | Q(user__isnull=True))

    def _visible_export_jobs_queryset(self, request):
        return ExportJob.objects.filter(Q(user=request.user) | Q(user__isnull=True))

    @action(detail=False, methods=["post"], url_path="exports")
    def create_export_job(self, request):
        serializer = ExportCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        normalized_ids = sorted(ids)
        output_format = serializer.validated_data["format"]
        resample_hz = serializer.validated_data.get(
            "resample_hz", settings.MOTEC_RESAMPLE_HZ_DEFAULT
        )

        logs = list(self._visible_logs_queryset(request).filter(id__in=normalized_ids))
        found_ids = {log.id for log in logs}
        missing_ids = sorted(set(normalized_ids) - found_ids)
        if missing_ids:
            return Response(
                {"error": f"Log IDs not found: {missing_ids}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        active_jobs = (
            self._visible_export_jobs_queryset(request)
            .filter(
                status__in=["pending", "processing"],
                format=output_format,
                resample_hz=resample_hz,
            )
            .order_by("-created_at")
        )
        for existing in active_jobs:
            existing_ids = sorted(existing.requested_ids or [])
            if existing_ids == normalized_ids:
                return Response(
                    ExportJobSerializer(existing).data, status=status.HTTP_200_OK
                )

        job = ExportJob.objects.create(
            user=request.user,
            format=output_format,
            resample_hz=resample_hz,
            status="pending",
            requested_ids=normalized_ids,
        )
        ExportItem.objects.bulk_create(
            [ExportItem(job=job, mcap_log=log, status="pending") for log in logs]
        )
        enqueue_export_job(job.id)

        return Response(ExportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"exports/(?P<job_id>[^/.]+)/status",
    )
    def export_status(self, request, job_id=None):
        if job_id is None:
            return Response(
                {"error": "Missing job id"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            job = (
                self._visible_export_jobs_queryset(request)
                .prefetch_related("items__mcap_log")
                .get(id=job_id)
            )
        except ExportJob.DoesNotExist:
            return Response(
                {"error": f"Export job {job_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        cached = cache.get(f"export_status:{job_id}")
        if cached:
            return Response(cached, status=status.HTTP_200_OK)

        return Response(ExportJobSerializer(job).data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"exports/(?P<job_id>[^/.]+)/download",
    )
    def export_download(self, request, job_id=None):
        try:
            job = self._visible_export_jobs_queryset(request).get(id=job_id)
        except ExportJob.DoesNotExist:
            return Response(
                {"error": f"Export job {job_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job.status not in ["completed", "completed_with_errors"] or not job.zip_uri:
            return Response(
                {
                    "error": "Export job is not ready yet",
                    "status": job.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not str(job.zip_uri).startswith(settings.MEDIA_URL):
            return Response(
                {"error": "Invalid export path"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        rel_path = str(job.zip_uri).replace(settings.MEDIA_URL, "", 1)
        zip_path = Path(settings.MEDIA_ROOT) / rel_path
        if not zip_path.exists():
            return Response(
                {"error": "Export bundle not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return FileResponse(
            open(zip_path, "rb"),
            as_attachment=True,
            filename=f"export_job_{job.id}.zip",
            content_type="application/zip",
        )

    @action(detail=False, methods=["get"], url_path="exports/active")
    def active_exports(self, request):
        jobs = (
            self._visible_export_jobs_queryset(request)
            .filter(
                status__in=["pending", "processing"],
            )
            .prefetch_related("items")
            .order_by("-created_at")
        )
        return Response(
            ExportJobSerializer(jobs, many=True).data, status=status.HTTP_200_OK
        )
