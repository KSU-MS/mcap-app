from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from rest_framework.test import APIClient

from .conversion.ld_writer import write_ld_file
from .conversion.mcap_converter import McapToCsvConverter
from .services.contracts import ConversionRequest, ExportProgressSnapshot
from .services.conversion_service import McapConversionService
from .services.status_constants import is_export_terminal, is_mcap_terminal
from .serializers import DownloadRequestSerializer, ExportCreateRequestSerializer
from .models import ExportJob, McapLog, Workspace, WorkspaceMember
from .conversion.telemetry_log import DataLog


class DownloadRequestSerializerTests(SimpleTestCase):
    def test_default_resample_rate_is_applied(self):
        serializer = DownloadRequestSerializer(data={"ids": [1], "format": "csv_omni"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["resample_hz"], 20.0)

    def test_resample_rate_range_is_enforced(self):
        serializer = DownloadRequestSerializer(
            data={"ids": [1], "format": "ld", "resample_hz": 0.5}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("resample_hz", serializer.errors)


class ExportCreateRequestSerializerTests(SimpleTestCase):
    def test_default_resample_rate_is_applied(self):
        serializer = ExportCreateRequestSerializer(
            data={"ids": [1], "format": "csv_tvn"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["resample_hz"], 20.0)


class McapConverterResampleTests(SimpleTestCase):
    def test_resample_timestamp_groups_returns_fixed_interval(self):
        converter = McapToCsvConverter()
        groups = {
            0: {"speed": "1"},
            500_000_000: {"speed": "2"},
            1_000_000_000: {"speed": "3"},
        }

        result = converter._resample_timestamp_groups(groups, 2.0)

        self.assertEqual([row[0] for row in result], [0, 500_000_000, 1_000_000_000])
        self.assertEqual(result[-1][1]["speed"], "3")


class DataLogTests(SimpleTestCase):
    def test_datalog_resample_aligns_channels_to_common_timebase(self):
        log = DataLog(name="test")
        log.add_sample("speed", 10.0, 1.0)
        log.add_sample("speed", 10.5, 2.0)
        log.add_sample("rpm", 10.25, 1000.0)
        log.add_sample("rpm", 10.75, 2000.0)

        log.resample(2.0)

        speed = log.channels["speed"].messages
        rpm = log.channels["rpm"].messages
        self.assertEqual(len(speed), len(rpm))
        self.assertEqual([m.timestamp for m in speed], [10.0, 10.5, 10.75])
        self.assertEqual([m.value for m in speed], [1.0, 2.0, 2.0])
        self.assertEqual([m.value for m in rpm], [0.0, 1000.0, 1000.0])


class McapConverterFieldExtractionTests(SimpleTestCase):
    class _Field:
        LABEL_REPEATED = 3

        def __init__(self, name, label=1):
            self.name = name
            self.label = label

    class _Proto:
        def ListFields(self):
            return [
                (McapConverterFieldExtractionTests._Field("speed"), 123.4),
                (McapConverterFieldExtractionTests._Field("gear"), 3),
                (McapConverterFieldExtractionTests._Field("valid"), True),
                (McapConverterFieldExtractionTests._Field("name"), "abc"),
                (
                    McapConverterFieldExtractionTests._Field(
                        "samples",
                        label=McapConverterFieldExtractionTests._Field.LABEL_REPEATED,
                    ),
                    [1, 2, 3],
                ),
            ]

    def test_iter_numeric_fields_filters_to_numeric_scalars(self):
        converter = McapToCsvConverter()
        values = converter._iter_numeric_fields(self._Proto())
        self.assertEqual(values, [("speed", 123.4), ("gear", 3.0), ("valid", 1.0)])


class LdWriterTests(SimpleTestCase):
    def test_write_ld_file_uses_native_backend_without_env(self):
        datalog = DataLog(name="test")
        datalog.add_sample("speed", 0.0, 1.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "native.ld"
            os.environ.pop("MOTEC_LD_WRITER_CMD", None)
            os.environ.pop("MOTEC_LOG_GENERATOR_DIR", None)
            write_ld_file(datalog, output_path, 20.0)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_write_ld_file_invokes_external_command(self):
        datalog = DataLog(name="test")
        datalog.add_sample("speed", 0.0, 1.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export.ld"
            os.environ["MOTEC_LD_WRITER_CMD"] = (
                "python -c \"open('{output}','wb').write(b'LD')\""
            )
            try:
                with patch(
                    "api.conversion.ld_writer.write_ld_native",
                    side_effect=RuntimeError("native failed"),
                ):
                    write_ld_file(datalog, output_path, 20.0)
                self.assertTrue(output_path.exists())
                self.assertEqual(output_path.read_bytes(), b"LD")
            finally:
                os.environ.pop("MOTEC_LD_WRITER_CMD", None)

    def test_write_ld_file_surfaces_writer_failure(self):
        datalog = DataLog(name="test")
        datalog.add_sample("speed", 0.0, 1.0)

        os.environ["MOTEC_LD_WRITER_CMD"] = 'python -c "import sys; sys.exit(4)"'
        try:
            with patch(
                "api.conversion.ld_writer.write_ld_native",
                side_effect=RuntimeError("native failed"),
            ):
                with self.assertRaises(RuntimeError):
                    write_ld_file(datalog, Path("/tmp/out.ld"), 20.0)
        finally:
            os.environ.pop("MOTEC_LD_WRITER_CMD", None)

    def test_write_ld_file_supports_motec_log_generator_dir(self):
        datalog = DataLog(name="test")
        datalog.add_sample("speed", 0.0, 1.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            generator_dir = Path(temp_dir) / "MotecLogGenerator"
            generator_dir.mkdir(parents=True, exist_ok=True)
            (generator_dir / "motec_log_generator.py").write_text("# stub\n")

            output_path = Path(temp_dir) / "export.ld"
            os.environ["MOTEC_LOG_GENERATOR_DIR"] = str(generator_dir)

            def _fake_run(command_parts, capture_output, text, cwd):
                output_path.write_bytes(b"LD")

                class _Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return _Result()

            try:
                with patch(
                    "api.conversion.ld_writer.write_ld_native",
                    side_effect=RuntimeError("native failed"),
                ):
                    with patch(
                        "api.conversion.ld_writer.subprocess.run", side_effect=_fake_run
                    ):
                        write_ld_file(datalog, output_path, 20.0)
                self.assertTrue(output_path.exists())
            finally:
                os.environ.pop("MOTEC_LOG_GENERATOR_DIR", None)


class ConversionServiceTests(SimpleTestCase):
    def test_convert_to_ld_delegates_to_converter_with_ld_format(self):
        class _StubConverter:
            def __init__(self):
                self.calls = []

            def convert_to_csv(self, source, output, format, resample_hz):
                self.calls.append(
                    {
                        "source": source,
                        "output": output,
                        "format": format,
                        "resample_hz": resample_hz,
                    }
                )
                return output

        stub = _StubConverter()
        service = McapConversionService(converter=stub)

        result = service.convert_to_ld("/tmp/in.mcap", "/tmp/out.ld", 25.0)

        self.assertEqual(result, "/tmp/out.ld")
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(stub.calls[0]["format"], "ld")
        self.assertEqual(stub.calls[0]["resample_hz"], 25.0)

    def test_convert_with_result_returns_error_without_raising(self):
        class _FailingConverter:
            def convert_to_csv(self, source, output, format, resample_hz):
                raise RuntimeError("boom")

        service = McapConversionService(converter=_FailingConverter())
        result = service.convert_with_result(
            ConversionRequest(
                source_path=Path("/tmp/in.mcap"),
                output_path=Path("/tmp/out.ld"),
                format_suffix="ld",
                resample_hz=20.0,
            )
        )
        self.assertFalse(result.success)
        self.assertIn("boom", result.error)


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
            format="ld",
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
    def test_tasks_module_exports_named_celery_tasks(self):
        from . import tasks as tasks_module

        self.assertEqual(
            tasks_module.recover_mcap_file.name, "api.tasks.recover_mcap_file"
        )
        self.assertEqual(tasks_module.parse_mcap_file.name, "api.tasks.parse_mcap_file")
        self.assertEqual(
            tasks_module.convert_export_item.name, "api.tasks.convert_export_item"
        )
        self.assertEqual(
            tasks_module.finalize_export_job.name, "api.tasks.finalize_export_job"
        )

    def test_conversion_modules_import_from_new_package(self):
        from .conversion.mcap_converter import McapToCsvConverter as NewConverter
        from .conversion.telemetry_log import DataLog as NewDataLog

        self.assertIsNotNone(NewConverter)
        self.assertIsNotNone(NewDataLog)


class ExportAuthAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="alice", password="password123"
        )
        self.other_user = get_user_model().objects.create_user(
            username="bob", password="password123"
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

    def test_export_status_allows_authenticated_workspace_access(self):
        public_job = ExportJob.objects.create(
            workspace=self.workspace,
            format="csv_omni",
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
            format="csv_tvn",
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
            format="ld",
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
            data={"ids": [private_log.id], "format": "csv_omni", "resample_hz": 20.0},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_workspace_member_cannot_access_other_workspace_job(self):
        private_job = ExportJob.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            format="csv_tvn",
            resample_hz=20.0,
            status="processing",
            requested_ids=[],
        )

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(
            f"/api/mcap-logs/exports/{private_job.id}/status/?workspace_id={self.workspace.id}"
        )

        self.assertEqual(response.status_code, 403)


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
