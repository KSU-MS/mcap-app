#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd: list[str]) -> tuple[float, subprocess.CompletedProcess[str]]:
    start = time.perf_counter()
    completed = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    return elapsed, completed


def must_json(stdout: str, label: str) -> dict:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not return valid JSON: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Go worker smoke test")
    parser.add_argument("--mcap", required=True, help="Absolute path to MCAP file")
    parser.add_argument(
        "--repo",
        default="/Users/pettruskonnoth/Documents/programming/mcap_query_backend",
        help="Repo root path",
    )
    parser.add_argument("--log-id", type=int, default=1004001)
    parser.add_argument("--gps-sample-step", type=int, default=10)
    parser.add_argument("--resample-hz", type=float, default=20.0)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    mcap_path = Path(args.mcap).resolve()
    if not mcap_path.exists():
        print(f"MCAP file not found: {mcap_path}", file=sys.stderr)
        return 2

    fanout_bin = repo / "go_worker" / "mcap_fanout_worker"
    export_bin = repo / "go_worker" / "export_convert_worker"
    media_root = repo / "backend" / "media"
    precomputed_dir = media_root / "precomputed" / str(args.log_id)

    for binary in [fanout_bin, export_bin]:
        if not binary.exists():
            print(f"Worker binary not found: {binary}", file=sys.stderr)
            return 2

    fanout_cmd = [
        str(fanout_bin),
        "--mode",
        "fanout",
        "--path",
        str(mcap_path),
        "--gps-sample-step",
        str(max(1, int(args.gps_sample_step))),
        "--generate-map-preview",
        "--log-id",
        str(args.log_id),
        "--media-root",
        str(media_root),
        "--media-url",
        "/media/",
    ]

    export_cmd = [
        str(export_bin),
        "--source",
        str(mcap_path),
        "--format",
        "all",
        "--output-dir",
        str(precomputed_dir),
        "--base-name",
        str(args.log_id),
        "--resample-hz",
        str(args.resample_hz),
    ]

    fanout_elapsed, fanout_proc = run_cmd(fanout_cmd)
    if fanout_proc.returncode != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "fanout",
                    "elapsed_seconds": round(fanout_elapsed, 3),
                    "error": (fanout_proc.stderr or fanout_proc.stdout).strip(),
                },
                indent=2,
            )
        )
        return 1
    fanout_payload = must_json(fanout_proc.stdout, "fanout")

    export_elapsed, export_proc = run_cmd(export_cmd)
    if export_proc.returncode != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "export_all",
                    "elapsed_seconds": round(export_elapsed, 3),
                    "error": (export_proc.stderr or export_proc.stdout).strip(),
                },
                indent=2,
            )
        )
        return 1
    export_payload = must_json(export_proc.stdout, "export_all")

    formats = export_payload.get("formats", {})
    required_formats = ["h5"]
    missing_or_failed = [
        fmt
        for fmt in required_formats
        if formats.get(fmt, {}).get("status") != "completed"
    ]

    report = {
        "ok": len(missing_or_failed) == 0,
        "mcap": str(mcap_path),
        "log_id": args.log_id,
        "timing": {
            "fanout_seconds": round(fanout_elapsed, 3),
            "conversion_all_seconds": round(export_elapsed, 3),
            "total_seconds": round(fanout_elapsed + export_elapsed, 3),
        },
        "fanout": {
            "channel_count": fanout_payload.get("summary", {}).get("channel_count"),
            "duration": fanout_payload.get("summary", {}).get("duration"),
            "gps_points": len(fanout_payload.get("gps", {}).get("all_coordinates", [])),
            "map_preview": fanout_payload.get("map_preview", {}),
        },
        "formats": formats,
        "required_format_failures": missing_or_failed,
        "precomputed_dir": str(precomputed_dir),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
