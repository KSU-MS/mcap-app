import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from .motec_ld_native import write_ld_native
from .telemetry_log import DataLog


def _build_payload(datalog: DataLog, frequency_hz: float) -> dict:
    channels = []
    for channel_name, channel in datalog.channels.items():
        channels.append(
            {
                "name": channel_name,
                "units": channel.units,
                "decimals": channel.decimals,
                "samples": [
                    {"timestamp": msg.timestamp, "value": msg.value}
                    for msg in channel.messages
                ],
            }
        )

    return {
        "name": datalog.name,
        "start": datalog.start(),
        "end": datalog.end(),
        "duration": datalog.duration(),
        "frequency_hz": frequency_hz,
        "channels": channels,
    }


def _write_csv_payload(datalog: DataLog, path: Path) -> None:
    channel_names = list(datalog.channels.keys())
    if not channel_names:
        raise RuntimeError("No channels available for LD conversion")

    first_channel = datalog.channels[channel_names[0]]
    with open(path, "w", encoding="utf-8") as csv_file:
        csv_file.write("Time," + ",".join(channel_names) + "\n")
        for idx, message in enumerate(first_channel.messages):
            row = [f"{message.timestamp:.9f}"]
            for channel_name in channel_names:
                samples = datalog.channels[channel_name].messages
                row.append(str(samples[idx].value if idx < len(samples) else ""))
            csv_file.write(",".join(row) + "\n")


def _run_external_command(command_parts: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(command_parts, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"LD writer command failed with exit code {result.returncode}: {details}"
        )
    return (result.stderr or result.stdout or "").strip()


def write_ld_file(datalog: DataLog, output_path: Path, frequency_hz: float) -> None:
    """Write LD via native writer with optional external fallbacks."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    native_error: Exception | None = None
    try:
        write_ld_native(datalog, output_path, frequency_hz)
        if output_path.exists():
            return
        native_error = RuntimeError("Native LD writer did not create an output file")
    except Exception as exc:
        native_error = exc

    command_template = os.getenv("MOTEC_LD_WRITER_CMD", "").strip()
    motec_generator_dir = os.getenv("MOTEC_LOG_GENERATOR_DIR", "").strip()

    if command_template:
        payload = _build_payload(datalog, frequency_hz)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as temp_json:
            json.dump(payload, temp_json)
            temp_json_path = Path(temp_json.name)

        try:
            formatted_command = command_template.format(
                input=str(temp_json_path),
                output=str(output_path),
                frequency=str(frequency_hz),
            )
            command_parts = shlex.split(formatted_command)
            _run_external_command(command_parts)
        finally:
            try:
                temp_json_path.unlink(missing_ok=True)
            except Exception:
                pass
    elif motec_generator_dir:
        generator_dir = Path(motec_generator_dir).expanduser().resolve()
        generator_script = generator_dir / "motec_log_generator.py"
        if not generator_script.exists():
            raise RuntimeError(
                f"MOTEC_LOG_GENERATOR_DIR is set to '{generator_dir}', but "
                "motec_log_generator.py was not found there."
            )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as temp_csv:
            temp_csv_path = Path(temp_csv.name)

        try:
            _write_csv_payload(datalog, temp_csv_path)
            command_parts = [
                "python3",
                str(generator_script),
                str(temp_csv_path),
                "CSV",
                "--output",
                str(output_path),
                "--frequency",
                str(frequency_hz),
            ]
            _run_external_command(command_parts, cwd=generator_dir)
        finally:
            try:
                temp_csv_path.unlink(missing_ok=True)
            except Exception:
                pass
    else:
        raise RuntimeError(
            "LD export backend is not configured. Set MOTEC_LD_WRITER_CMD with "
            "placeholders {input}, {output}, {frequency}, or set MOTEC_LOG_GENERATOR_DIR "
            f"to a MotecLogGenerator checkout. Native writer error: {native_error}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"LD writer command completed but no output file was created at {output_path}"
        )
