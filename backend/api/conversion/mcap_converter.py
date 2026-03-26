"""MCAP to CSV/LD converter module."""

import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mcap.reader import make_reader
from mcap_protobuf.decoder import DecoderFactory

from .ld_writer import write_ld_file
from .telemetry_log import DataLog


class McapToCsvConverter:
    """Converts MCAP files to CSV/LD format with Protobuf decoding."""

    def __init__(self):
        self.decoder_factory = DecoderFactory()

    def convert(
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
                datalog = self._build_datalog_from_mcap(
                    file_handle, mcap_file_path.stem
                )

            if not datalog.channels:
                raise RuntimeError("No numeric scalar protobuf fields found in MCAP")

            datalog.resample(resample_hz)

            if format == "tvn":
                self._write_csv_tvn(output_file_path, datalog)
            elif format == "omni":
                self._write_csv_omni(output_file_path, datalog)
            elif format == "ld":
                self._write_ld(output_file_path, datalog, resample_hz)

        except Exception as e:
            raise RuntimeError(f"Error converting MCAP to {format.upper()}: {e}") from e

        return str(output_file_path)

    def convert_to_csv(
        self,
        mcap_path: str,
        output_path: str,
        format: str = "omni",
        resample_hz: float | None = None,
    ) -> str:
        """Backward-compatible wrapper for existing callers."""
        return self.convert(
            mcap_path, output_path, format=format, resample_hz=resample_hz
        )

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

    def _build_datalog_from_mcap(self, file_handle, log_name: str = "") -> DataLog:
        """Parse an MCAP file into a numeric DataLog structure."""
        reader = make_reader(file_handle, decoder_factories=[self.decoder_factory])
        datalog = DataLog(name=log_name)

        for _, channel, message, proto_msg in reader.iter_decoded_messages():
            timestamp_seconds = float(message.log_time) / 1_000_000_000.0
            prefix = ""
            schema_name = getattr(channel, "topic", "")
            if schema_name:
                prefix = f"{schema_name}."
            for field_name, value in self._iter_numeric_fields(proto_msg):
                channel_name = f"{prefix}{field_name}" if prefix else field_name
                datalog.add_sample(channel_name, timestamp_seconds, value)

        return datalog

    def _iter_numeric_fields(self, proto_msg) -> list[tuple[str, float]]:
        values: list[tuple[str, float]] = []
        for field_desc, field_value in proto_msg.ListFields():
            if field_desc.label == field_desc.LABEL_REPEATED:
                continue
            if isinstance(field_value, bool):
                values.append((field_desc.name, 1.0 if field_value else 0.0))
            elif isinstance(field_value, (int, float)):
                values.append((field_desc.name, float(field_value)))
        return values

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
        datalog: DataLog,
    ) -> None:
        """Write TVN CSV output from the fixed-rate common timebase."""
        channel_names = list(datalog.channels.keys())
        if not channel_names:
            raise RuntimeError("No channels available for TVN output")

        first_channel = datalog.channels[channel_names[0]]
        timestamps = [
            int(round(msg.timestamp * 1_000_000_000)) for msg in first_channel.messages
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Time", "Name", "Value"])

            for idx, timestamp in enumerate(timestamps):
                for channel_name in channel_names:
                    messages = datalog.channels[channel_name].messages
                    if idx >= len(messages):
                        continue
                    writer.writerow([timestamp, channel_name, messages[idx].value])

    def _write_csv_omni(
        self,
        output_path: Path,
        datalog: DataLog,
    ) -> None:
        """Write OMNI CSV output with one column per channel."""
        channel_names = list(datalog.channels.keys())
        if not channel_names:
            raise RuntimeError("No channels available for OMNI output")

        first_channel = datalog.channels[channel_names[0]]
        timestamps = [
            int(round(msg.timestamp * 1_000_000_000)) for msg in first_channel.messages
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Time", *channel_names])

            for idx, timestamp in enumerate(timestamps):
                row: List[Any] = [timestamp]
                for channel_name in channel_names:
                    messages = datalog.channels[channel_name].messages
                    row.append(messages[idx].value if idx < len(messages) else "")
                writer.writerow(row)

    def _write_ld(
        self,
        output_path: Path,
        datalog: DataLog,
        resample_hz: float,
    ) -> None:
        """Write LD output through configured external writer."""
        write_ld_file(datalog, output_path, resample_hz)
