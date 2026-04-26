from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from rest_framework.test import APIClient

from .services.contracts import ExportProgressSnapshot
from .services.status_constants import is_export_terminal, is_mcap_terminal
from .serializers import DownloadRequestSerializer, ExportCreateRequestSerializer
from .models import ExportItem, ExportJob, McapLog, Workspace, WorkspaceMember
from .tasks import is_non_retryable_recover_error


class DownloadRequestSerializerTests(SimpleTestCase):
    def test_default_format_is_mcap(self):
        serializer = DownloadRequestSerializer(data={"ids": [1]})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["format"], "mcap")

    def test_default_resample_rate_is_applied(self):
        serializer = DownloadRequestSerializer(data={"ids": [1], "format": "mcap"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["resample_hz"], 20.0)

    def test_resample_rate_range_is_enforced(self):
        serializer = DownloadRequestSerializer(
            data={"ids": [1], "format": "mcap", "resample_hz": 0.5}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("resample_hz", serializer.errors)


class ExportCreateRequestSerializerTests(SimpleTestCase):
    def test_default_resample_rate_is_applied(self):
        serializer = ExportCreateRequestSerializer(data={"ids": [1], "format": "h5"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["resample_hz"], 20.0)


class RecoverTaskErrorClassificationTests(SimpleTestCase):
    def test_invalid_magic_is_non_retryable(self):
        error = RuntimeError(
            "mcap recover failed: failed to recover: Invalid magic at start of file"
        )
        self.assertTrue(is_non_retryable_recover_error(error))

    def test_transient_error_remains_retryable(self):
        error = RuntimeError("temporary io error")
        self.assertFalse(is_non_retryable_recover_error(error))


class StatusConstantsTests(SimpleTestCase):
    def test_is_mcap_terminal_handles_error_prefix(self):
        self.assertTrue(is_mcap_terminal("error: failed to parse"))
        self.assertTrue(is_mcap_terminal("completed"))
        self.assertFalse(is_mcap_terminal("processing"))

    def test_is_export_terminal_matches_terminal_states(self):
        self.assertTrue(is_export_terminal("completed"))
        self.assertTrue(is_export_terminal("completed_with_errors"))
        self.assertFalse(is_export_terminal("processing"))


class ContractsTests(SimpleTestCase):
    def test_export_progress_snapshot_payload_shape(self):
        snapshot = ExportProgressSnapshot(
            id=7,
            status="processing",
            format="h5",
            resample_hz=20.0,
            error_message=None,
            total_items=4,
            completed_items=1,
            failed_items=0,
            progress_percent=25,
        )
        payload = snapshot.to_payload()
        self.assertEqual(payload["id"], 7)
        self.assertEqual(payload["progress_percent"], 25)


class TaskSplitCompatibilityTests(SimpleTestCase):
    def test_tasks_module_exports_background_job_helpers(self):
        from . import tasks as tasks_module

        self.assertTrue(callable(tasks_module.recover_mcap_file))
        self.assertTrue(callable(tasks_module.parse_mcap_file))
        self.assertTrue(callable(tasks_module.enqueue_export_job))


class ExportAuthAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="alice", password="password123"
        )
        self.other_user = get_user_model().objects.create_user(
            username="bob", password="password123"
        )
        self.viewer_user = get_user_model().objects.create_user(
            username="viewer", password="password123"
        )
        self.editor_user = get_user_model().objects.create_user(
            username="editor", password="password123"
        )
        self.workspace = Workspace.objects.create(name="Team", slug="team")
        self.other_workspace = Workspace.objects.create(name="Other", slug="other")
        WorkspaceMember.objects.create(
            user=self.user, workspace=self.workspace, role=WorkspaceMember.ROLE_ADMIN
        )
        WorkspaceMember.objects.create(
            user=self.other_user,
            workspace=self.other_workspace,
            role=WorkspaceMember.ROLE_VIEWER,
        )
        WorkspaceMember.objects.create(
            user=self.viewer_user,
            workspace=self.workspace,
            role=WorkspaceMember.ROLE_VIEWER,
        )
        WorkspaceMember.objects.create(
            user=self.editor_user,
            workspace=self.workspace,
            role=WorkspaceMember.ROLE_EDITOR,
        )

    def test_export_status_allows_authenticated_workspace_access(self):
        public_job = ExportJob.objects.create(
            workspace=self.workspace,
            format="h5",
            resample_hz=20.0,
            status="processing",
            requested_ids=[],
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f"/api/mcap-logs/exports/{public_job.id}/status/?workspace_id={self.workspace.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], public_job.id)

    def test_export_status_requires_authentication(self):
        private_job = ExportJob.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            format="h5",
            resample_hz=20.0,
            status="processing",
            requested_ids=[],
        )

        response = self.client.get(f"/api/mcap-logs/exports/{private_job.id}/status/")

        self.assertEqual(response.status_code, 403)

    def test_export_download_requires_authentication(self):
        private_job = ExportJob.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            format="h5",
            resample_hz=20.0,
            status="completed",
            requested_ids=[],
            zip_uri="/media/exports/999/bundle.zip",
        )

        response = self.client.get(f"/api/mcap-logs/exports/{private_job.id}/download/")

        self.assertEqual(response.status_code, 403)

    def test_create_export_job_requires_authentication(self):
        private_log = McapLog.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            file_name="private.mcap",
        )

        response = self.client.post(
            "/api/mcap-logs/exports/",
            data={"ids": [private_log.id], "format": "h5", "resample_hz": 20.0},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_workspace_member_cannot_access_other_workspace_job(self):
        private_job = ExportJob.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            format="h5",
            resample_hz=20.0,
            status="processing",
            requested_ids=[],
        )

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(
            f"/api/mcap-logs/exports/{private_job.id}/status/?workspace_id={self.workspace.id}"
        )

        self.assertEqual(response.status_code, 403)

    def test_workspace_viewer_can_list_logs(self):
        McapLog.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            file_name="shared.mcap",
        )

        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.get(f"/api/mcap-logs/?workspace_id={self.workspace.id}")

        self.assertEqual(response.status_code, 200)

    def test_workspace_viewer_cannot_update_log(self):
        log = McapLog.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            file_name="shared.mcap",
        )

        self.client.force_authenticate(user=self.viewer_user)
        response = self.client.patch(
            f"/api/mcap-logs/{log.id}/?workspace_id={self.workspace.id}",
            data={"notes": "viewer-edit"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_workspace_editor_can_update_log(self):
        log = McapLog.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            file_name="shared.mcap",
        )

        self.client.force_authenticate(user=self.editor_user)
        response = self.client.patch(
            f"/api/mcap-logs/{log.id}/?workspace_id={self.workspace.id}",
            data={"notes": "editor-edit"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notes"], "editor-edit")


class AuthSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.username = "session-user"
        self.password = "password123"
        get_user_model().objects.create_user(
            username=self.username,
            password=self.password,
            email="session@example.com",
        )

    def test_login_me_logout_roundtrip(self):
        csrf_response = self.client.get("/api/auth/csrf/")
        self.assertEqual(csrf_response.status_code, 200)
        csrf_token = csrf_response.cookies.get("csrftoken").value

        login_response = self.client.post(
            "/api/auth/login/",
            data={"username": self.username, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.data["username"], self.username)

        me_response = self.client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["username"], self.username)

        logout_response = self.client.post(
            "/api/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=self.client.cookies.get("csrftoken").value,
        )
        self.assertEqual(logout_response.status_code, 204)

        me_after_logout = self.client.get("/api/auth/me/")
        self.assertEqual(me_after_logout.status_code, 403)
