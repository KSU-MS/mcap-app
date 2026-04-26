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
from .services.background_jobs import enqueue_export_job
from .workspace import resolve_workspace_for_request


class ExportActionsMixin:
    @staticmethod
    def _mcap_has_user_field():
        return any(field.name == "user" for field in McapLog._meta.get_fields())

    @staticmethod
    def _export_job_has_user_field():
        return any(field.name == "user" for field in ExportJob._meta.get_fields())

    @staticmethod
    def _mcap_has_workspace_field():
        return any(field.name == "workspace" for field in McapLog._meta.get_fields())

    @staticmethod
    def _export_job_has_workspace_field():
        return any(field.name == "workspace" for field in ExportJob._meta.get_fields())

    @staticmethod
    def _export_job_has_created_by_field():
        return any(field.name == "created_by" for field in ExportJob._meta.get_fields())

    def _visible_logs_queryset(self, request):
        workspace = getattr(self, "workspace", None) or resolve_workspace_for_request(
            request
        )
        if workspace is None:
            return McapLog.objects.none()
        if self._mcap_has_workspace_field():
            return McapLog.objects.filter(workspace=workspace)
        if not self._mcap_has_user_field():
            return McapLog.objects.all()
        return McapLog.objects.filter(Q(user=request.user) | Q(user__isnull=True))

    def _visible_export_jobs_queryset(self, request):
        workspace = getattr(self, "workspace", None) or resolve_workspace_for_request(
            request
        )
        if workspace is None:
            return ExportJob.objects.none()
        if self._export_job_has_workspace_field():
            return ExportJob.objects.filter(workspace=workspace)
        if not self._export_job_has_user_field():
            return ExportJob.objects.all()
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

        create_kwargs = {
            "format": output_format,
            "resample_hz": resample_hz,
            "status": "pending",
            "requested_ids": normalized_ids,
        }
        workspace = getattr(self, "workspace", None) or resolve_workspace_for_request(
            request
        )
        if workspace is not None and self._export_job_has_workspace_field():
            create_kwargs["workspace"] = workspace
        if self._export_job_has_created_by_field():
            create_kwargs["created_by"] = request.user
        if self._export_job_has_user_field():
            create_kwargs["user"] = request.user
        job = ExportJob.objects.create(**create_kwargs)
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
