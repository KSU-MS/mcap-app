"""MCAP to CSV/LD converter module."""

import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mcap.reader import make_reader
from mcap_protobuf.decoder import DecoderFactory


class McapToCsvConverter:
    """Converts MCAP files to CSV/LD format with Protobuf decoding."""

    def __init__(self):
        self.decoder_factory = DecoderFactory()

    def convert_to_csv(
        self,
        mcap_path: str,
        output_path: str,
        format: str = "omni",
        resample_hz: float | None = None,
    ) -> str:
        """Convert an MCAP file to CSV/LD format."""
        mcap_file_path = Path(mcap_path)
        if not mcap_file_path.exists():
            raise FileNotFoundError(f"MCAP file not found: {mcap_file_path}")

        if format not in ["omni", "tvn", "ld"]:
            raise ValueError(
                f"Invalid format: {format}. Must be 'omni', 'tvn', or 'ld'"
            )

        if resample_hz is None:
            resample_hz = 20.0
        if resample_hz <= 0:
            raise ValueError("resample_hz must be greater than 0")

        output_file_path = Path(output_path)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(mcap_file_path, "rb") as file_handle:
                grouped_data, topics = self._parse_mcap(file_handle)

            if format == "tvn":
                self._write_csv_tvn(output_file_path, grouped_data, topics, resample_hz)
            elif format == "omni":
                self._write_csv_omni(
                    output_file_path, grouped_data, topics, resample_hz
                )
            elif format == "ld":
                self._write_ld(output_file_path, grouped_data, topics, resample_hz)

        except Exception as e:
            raise RuntimeError(f"Error converting MCAP to {format.upper()}: {e}") from e

        return str(output_file_path)

    def _parse_mcap(self, file_handle) -> Tuple[Dict[int, Dict[str, Any]], List[str]]:
        """Parse an MCAP file into timestamp groups and ordered topics."""
        reader = make_reader(file_handle, decoder_factories=[self.decoder_factory])

        timestamp_groups: Dict[int, Dict[str, Any]] = {}
        topics: List[str] = []
        seen_topics: set[str] = set()

        for _, _, message, proto_msg in reader.iter_decoded_messages():
            timestamp_ns = int(message.log_time)
            row = timestamp_groups.setdefault(timestamp_ns, {})

            for field in proto_msg.DESCRIPTOR.fields:
                name = field.name
                if name not in seen_topics:
                    seen_topics.add(name)
                    topics.append(name)

                try:
                    field_value = getattr(proto_msg, name)
                    row[name] = self._convert_value(field_value)
                except Exception:
                    continue

        return timestamp_groups, topics

    def _convert_value(self, value: Any) -> str:
        """Convert a Protobuf field value to a string representation."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, bytes):
            return value.hex() if len(value) < 100 else "[binary data]"
        if isinstance(value, list):
            return ",".join(str(self._convert_value(item)) for item in value)
        return str(value)

    def _resample_timestamp_groups(
        self,
        timestamp_groups: Dict[int, Dict[str, Any]],
        resample_hz: float,
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """Resample grouped data to a fixed frequency in nanoseconds."""
        if not timestamp_groups:
            return []

        source_timestamps = sorted(timestamp_groups.keys())
        if len(source_timestamps) == 1:
            ts = source_timestamps[0]
            return [(ts, dict(timestamp_groups[ts]))]

        start_ns = source_timestamps[0]
        end_ns = source_timestamps[-1]
        step_ns = max(1, int(round(1_000_000_000 / resample_hz)))

        resampled: List[Tuple[int, Dict[str, Any]]] = []
        source_idx = 0
        current_values: Dict[str, Any] = {}

        current_ns = start_ns
        while current_ns <= end_ns:
            while (
                source_idx < len(source_timestamps)
                and source_timestamps[source_idx] <= current_ns
            ):
                current_values.update(timestamp_groups[source_timestamps[source_idx]])
                source_idx += 1

            resampled.append((current_ns, dict(current_values)))
            current_ns += step_ns

        if resampled[-1][0] != end_ns:
            while source_idx < len(source_timestamps):
                current_values.update(timestamp_groups[source_timestamps[source_idx]])
                source_idx += 1
            resampled.append((end_ns, dict(current_values)))

        return resampled

    def _write_csv_tvn(
        self,
        output_path: Path,
        timestamp_groups: Dict[int, Dict[str, Any]],
        topics: List[str],
        resample_hz: float,
    ) -> None:
        """Write TVN CSV output from the fixed-rate common timebase."""
        resampled_rows = self._resample_timestamp_groups(timestamp_groups, resample_hz)

        with open(output_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Time", "Name", "Value"])

            for timestamp, topic_values in resampled_rows:
                for topic in topics:
                    if topic in topic_values:
                        writer.writerow([timestamp, topic, topic_values[topic]])

    def _write_csv_omni(
        self,
        output_path: Path,
        timestamp_groups: Dict[int, Dict[str, Any]],
        topics: List[str],
        resample_hz: float,
    ) -> None:
        """Write OMNI CSV output with one column per channel."""
        resampled_rows = self._resample_timestamp_groups(timestamp_groups, resample_hz)

        with open(output_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Time", *topics])

            for timestamp, topic_values in resampled_rows:
                row: List[Any] = [timestamp]
                for topic in topics:
                    row.append(topic_values.get(topic))
                writer.writerow(row)

    def _write_ld(
        self,
        output_path: Path,
        timestamp_groups: Dict[int, Dict[str, Any]],
        topics: List[str],
        resample_hz: float,
    ) -> None:
        """Write LD output placeholder with fixed-rate metadata."""
        resampled_rows = self._resample_timestamp_groups(timestamp_groups, resample_hz)

        with open(output_path, "w", encoding="utf-8") as file:
            file.write("# LD Format (placeholder)\n")
            file.write("# This format is not yet fully implemented\n")
            file.write(f"# Requested resample_hz: {resample_hz}\n")
            file.write(f"# Source points: {len(timestamp_groups)}\n")
            file.write(f"# Resampled points: {len(resampled_rows)}\n")
            file.write(f"# Topics: {len(topics)}\n")
            file.write(f"# Topics: {', '.join(topics)}\n")
