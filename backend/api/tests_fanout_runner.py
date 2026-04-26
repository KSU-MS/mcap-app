from django.test import SimpleTestCase, override_settings
from unittest.mock import patch

from api.services.mcap_fanout_runner import run_mcap_fanout


class McapFanoutRunnerTests(SimpleTestCase):
    @override_settings(MCAP_FANOUT_ENGINE="go")
    @patch("api.services.mcap_fanout_runner._run_go_fanout")
    def test_go_engine_uses_go_fanout(self, go_fanout_mock):
        go_fanout_mock.return_value = {"summary": {}, "gps": {}}

        result = run_mcap_fanout("/tmp/a.mcap", gps_sample_step=5)

        self.assertEqual(result, {"summary": {}, "gps": {}})
        go_fanout_mock.assert_called_once_with(
            "/tmp/a.mcap",
            gps_sample_step=5,
            log_id=None,
            generate_map_preview=False,
        )

    @override_settings(MCAP_FANOUT_ENGINE="python")
    def test_non_go_engine_raises(self):
        with self.assertRaises(RuntimeError):
            run_mcap_fanout("/tmp/a.mcap")
