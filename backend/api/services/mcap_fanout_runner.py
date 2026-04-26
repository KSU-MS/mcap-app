import json
import tempfile
import shlex
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings


def run_mcap_fanout(
    path: str,
    *,
    gps_sample_step: int = 10,
    log_id: int | None = None,
    generate_map_preview: bool = False,
) -> dict[str, dict[str, Any]]:
    engine = str(getattr(settings, "MCAP_FANOUT_ENGINE", "go") or "go").lower()
    if engine != "go":
        raise RuntimeError(
            "Only Go fanout engine is supported. Set MCAP_FANOUT_ENGINE=go."
        )
    return _run_go_fanout(
        path,
        gps_sample_step=gps_sample_step,
        log_id=log_id,
        generate_map_preview=generate_map_preview,
    )


def run_map_preview_from_coords(
    *,
    log_id: int,
    coords: list[tuple[float, float]],
) -> dict[str, Any]:
    payload = [[float(lon), float(lat)] for lon, lat in coords]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=True
    ) as temp_file:
        json.dump(payload, temp_file)
        temp_file.flush()
        command = _base_command()
        command.extend(
            [
                "--mode",
                "map-preview",
                "--log-id",
                str(int(log_id)),
                "--coords-path",
                temp_file.name,
                "--media-root",
                str(settings.MEDIA_ROOT),
                "--media-url",
                str(settings.MEDIA_URL),
            ]
        )
        payload = _run_go_command(command)

    map_preview = payload.get("map_preview")
    if not isinstance(map_preview, dict):
        raise RuntimeError(
            "Go map preview worker payload must contain map_preview object"
        )
    return map_preview


def _base_command() -> list[str]:
    command_str = str(
        getattr(
            settings, "MCAP_FANOUT_GO_CMD", "go run ./go_worker/cmd/mcap_fanout_worker"
        )
        or "go run ./go_worker/cmd/mcap_fanout_worker"
    ).strip()
    if not command_str:
        raise RuntimeError("MCAP_FANOUT_GO_CMD is empty")
    return shlex.split(command_str)


def _run_go_fanout(
    path: str,
    *,
    gps_sample_step: int,
    log_id: int | None,
    generate_map_preview: bool,
) -> dict[str, dict[str, Any]]:
    command = _base_command()
    command.extend(
        [
            "--mode",
            "fanout",
            "--path",
            str(path),
            "--gps-sample-step",
            str(max(1, int(gps_sample_step))),
        ]
    )
    if generate_map_preview:
        if log_id is None:
            raise RuntimeError("log_id is required when generate_map_preview=True")
        command.extend(
            [
                "--generate-map-preview",
                "--log-id",
                str(int(log_id)),
                "--media-root",
                str(settings.MEDIA_ROOT),
                "--media-url",
                str(settings.MEDIA_URL),
            ]
        )

    payload = _run_go_command(command)

    summary = payload.get("summary")
    gps = payload.get("gps")
    if not isinstance(summary, dict) or not isinstance(gps, dict):
        raise RuntimeError(
            "Go fanout worker payload must contain summary and gps objects"
        )

    result: dict[str, dict[str, Any]] = {
        "summary": summary,
        "gps": gps,
    }
    map_preview = payload.get("map_preview")
    if isinstance(map_preview, dict):
        result["map_preview"] = map_preview
    return result


def _run_go_command(command: list[str]) -> dict[str, Any]:
    timeout_seconds = int(getattr(settings, "MCAP_FANOUT_TIMEOUT_SECONDS", 600) or 600)
    repo_root = Path(settings.BASE_DIR).resolve().parent

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        error_message = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"Go fanout worker failed with exit code {completed.returncode}: {error_message}"
        )

    raw = (completed.stdout or "").strip()
    if not raw:
        raise RuntimeError("Go fanout worker returned empty output")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Go fanout worker returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Go fanout worker payload must be a JSON object")

    return payload
