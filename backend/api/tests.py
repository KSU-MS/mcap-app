from django.test import SimpleTestCase

from .mcap_converter import McapToCsvConverter
from .serializers import DownloadRequestSerializer, ExportCreateRequestSerializer


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
