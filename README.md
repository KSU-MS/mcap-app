#  MCAP Log API

A Django REST Framework backend for managing and parsing **Formula SAE telemetry logs** recorded in the `.mcap` format.

## Monorepo layout
- `backend/` — Django + DRF API (PostGIS)
- `frontend/` — Next.js client (pnpm)
- `go_worker/` — Go workers (`job_runner`, `mcap_fanout_worker`, `export_convert_worker`)

### Worker architecture
- `go_worker/cmd/job_runner` — DB-backed background job processor (`ingest_pipeline`, `export_job`, `map_preview`)
- `go_worker/cmd/mcap_fanout_worker` — ingest fanout for summary/GPS/map preview
- `go_worker/cmd/export_convert_worker` — conversion worker for `h5`
- `backend/api/services/background_jobs.py` — enqueue-only helpers (no Python job execution path)

### Quick start (host mode: app on host, DB in Docker)
- Copy env file: `cp .env.example .env`
- Update `.env` for host networking:
  - `DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5433/mcap_query_db`
  - `POSTGRES_HOST=127.0.0.1`
  - `POSTGRES_PORT=5433`
  - `MOTEC_LOG_GENERATOR_DIR=/absolute/path/to/MotecLogGenerator`
- Start infrastructure: `docker compose up -d`
- Sync backend deps: `uv sync`
- Migrate DB: `uv run python backend/manage.py migrate`
- Run backend API:
  - `cd backend && uv run daphne -b 127.0.0.1 -p 8000 backend.asgi:application`
- Run background jobs worker (separate terminal):
  - Go runner (ingest + export + map preview):
    - `cd go_worker && go build -o mcap_fanout_worker ./cmd/mcap_fanout_worker`
    - `cd go_worker && go build -o export_convert_worker ./cmd/export_convert_worker`
    - Optional native H5 build (requires HDF5 dev libs): `cd go_worker && PKG_CONFIG_PATH=/opt/homebrew/opt/hdf5/lib/pkgconfig CGO_CFLAGS='-I/opt/homebrew/opt/hdf5/include' CGO_LDFLAGS='-L/opt/homebrew/opt/hdf5/lib' go build -tags hdf5 -o export_convert_worker ./cmd/export_convert_worker`
    - `cd go_worker && go build -o job_runner ./cmd/job_runner`
    - `DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5433/mcap_query_db MCAP_FANOUT_GO_CMD=./mcap_fanout_worker MCAP_EXPORT_CMD=./export_convert_worker ./job_runner`
    - Ingest precomputes `h5` artifacts by default (`INGEST_PRECOMPUTE_EXPORTS=true`) under `MEDIA_ROOT/precomputed/<mcap_log_id>/`.
    - Ingest result status is `completed_with_errors` when any precomputed format fails.
    - `uv run python backend/manage.py process_jobs` is retired and should not be used.
- Run frontend:
  - `cd frontend && pnpm install && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run dev`

### Docker Compose
- This repo now uses a single Compose file for local dev infra: `compose.yml`
- Start DB: `docker compose up -d`
- Stop DB: `docker compose down`

Port defaults are env-driven. Copy `.env.example` to `.env` (for Docker Compose) and override any of:
`DATABASE_URL`, `POSTGRES_CONTAINER_PORT`, `POSTGRES_HOST_PORT`, `NGINX_HOST_PORT`, `DJANGO_HOST`, `DJANGO_PORT`, `FRONTEND_PORT`.

The service automates:
- Getting MCAP log files from the car’s onboard Pi
- Running `mcap recover` on every uploaded file
- Parsing recovered logs for:
  - Available channels (topics)
  - Start and end timestamps
  - Duration and channel count
- Storing all metadata in a relational database for easy querying
- Precomputing conversion artifacts at ingest: `h5`

Users can manually tag each log with:
- Car model  
- Driver  
- Event type  
- Notes  

---

## API Overview

| Method | Endpoint | Description |
|:--|:--|:--|
| `POST` | `/mcap-logs/` | Upload or register a new MCAP file. Automatically runs recovery and parsing. |
| `GET` | `/mcap-logs/` | List parsed logs. Supports filters for date, car, driver, event, and location. |
| `GET` | `/mcap-logs/{id}/` | Retrieve full metadata for one log. |
| `PATCH` | `/mcap-logs/{id}/` | Update manual tags (car, driver, event type, notes). |
| `GET` | `/mcap-logs/{id}/channels/` | View all available channels in a given log. |
| `POST` | `/mcap-logs/{id}/recover` | Re-run MCAP recovery (admin/debug only). |
| `POST` | `/mcap-logs/{id}/parse` | Re-run parsing (admin/debug only). |

---

## Summary

Each MCAP file becomes one database record with:
- `recovery_status` and `parse_status`
- `captured_at`, `duration_seconds`, `channel_count`
- `channels_summary` (JSON array of topics)
- Optional tags for `car`, `driver`, `event_type`, `notes`

This data can then be searched or displayed in a frontend dashboard  
(e.g., Next.js client for your FSAE team’s data analysis).

---

---
