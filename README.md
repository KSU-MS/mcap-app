#  MCAP Log API

A Django REST Framework backend for managing and parsing **Formula SAE telemetry logs** recorded in the `.mcap` format.

## Monorepo layout
- `backend/` — Django + Celery API (PostGIS/Redis)
- `frontend/` — Next.js client (pnpm)

### Backend conversion architecture
- `backend/api/conversion/` — MCAP decode, telemetry normalization, and format writers (`csv_omni`, `csv_tvn`, `ld`)
- `backend/api/services/conversion_service.py` — facade entrypoint used by Celery/export workflows
- `backend/api/services/contracts.py` — typed request/result/progress contracts for conversion and caching
- `backend/api/jobs/tasks_ingest.py` — recover/parse/gps/map pipeline tasks
- `backend/api/jobs/tasks_export.py` — export item conversion + bundle finalization tasks
- `backend/api/jobs/tasks_status.py` — cache payload builders for polling endpoints
- `backend/api/tasks.py` — compatibility export module for task imports and Celery task names

### Quick start (uv + Docker infra, no Nix required)
- Copy env file: `cp .env.example .env`
- Start infrastructure: `docker compose -f compose.dev.yml up -d`
- Sync backend deps: `uv sync`
- Migrate DB: `uv run python backend/manage.py migrate`
- Run backend API: `uv run python backend/manage.py runserver ${DJANGO_HOST:-127.0.0.1}:${DJANGO_PORT:-8000}`
- Run Celery worker (separate terminal): `uv run celery -A backend worker --loglevel=info`
- Run frontend: `cd frontend && pnpm install && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run dev`

### Full stack with Docker Compose
- `cp .env.example .env`
- `docker compose -f compose.prod.yml up -d --build`
- open `http://localhost:13000`

### Makefile shortcuts
- Local infra up/down:
  - `make dev-up`
  - `make dev-down`
- Production stack up/down:
  - `make prod-up`
  - `make prod-down`

### Optional Nix workflow
- Enter dev shell: `nix develop`
- Run optional reproducibility checks: `nix flake check`

### Reproducible Docker stack from Nix (no Dockerfile)
- Build app images with Nix on Linux (`x86_64-linux` or `aarch64-linux`):
  - `nix build .#packages.x86_64-linux.docker-backend .#packages.x86_64-linux.docker-celery .#packages.x86_64-linux.docker-migrate .#packages.x86_64-linux.docker-frontend`
- Load images into Docker on that Linux host:
  - `nix run .#packages.x86_64-linux.docker-load-images`
- Start full stack (internal networking, only nginx exposed):
  - `docker compose -f compose.nix.yml up -d`
- open `http://localhost:13000`

Port defaults are env-driven. Copy `.env.example` to `.env` (for Docker Compose) and override any of:
`DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `POSTGRES_CONTAINER_PORT`, `POSTGRES_HOST_PORT`, `REDIS_CONTAINER_PORT`, `REDIS_HOST_PORT`, `NGINX_HOST_PORT`, `DJANGO_HOST`, `DJANGO_PORT`, `FRONTEND_PORT`.

The service automates:
- Getting MCAP log files from the car’s onboard Pi
- Running `mcap recover` on every uploaded file
- Parsing recovered logs for:
  - Available channels (topics)
  - Start and end timestamps
  - Duration and channel count
- Storing all metadata in a relational database for easy querying

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

## To-Do Checklist

###  Core API
- [X] Create `McapLog` model  
- [X] Add `Car`, `Driver`, and `EventType` models  
- [X] Implement `McapLogSerializer`  
- [X] Implement `McapLogViewSet` with CRUD routes  
- [X] Add router URLs (`/mcap-logs/`)


###  Parsing
- [X] Use `mcap.reader` to extract:
  - [X] `captured_at` (from message start time)
  - [X] `duration_seconds`
  - [X] `channel_count`
  - [X] `channels_summary` (topics list)
- [X]  Parse GPS to get `race location`
- [ ] Background job system (Celary) to mass ingest data and parse it

###  Database + Metadata
- [X] Add fields for `recovery_status` and `parse_status`
- [X] Add foreign keys for `car`, `driver`, `event_type`
- [X] Add `notes`, `created_at`, and `updated_at`
- [X] Create migrations and migrate

###  Endpoints & Actions
- [X] `POST /mcap-logs/{id}/geojson/` - runs the Visvalingam algo to find important points and returns geoJson
- [ ] `POST /mcap-logs/` — upload + recover + parse  
- [X] `GET /mcap-logs/` — list all logs with filters  
- [ ] `GET /mcap-logs/{id}/` — view single log  
- [ ] `PATCH /mcap-logs/{id}/` — update tags  
- [ ] `GET /mcap-logs/{id}/channels/` — list channels  
- [ ] (Optional) `POST /mcap-logs/{id}/recover` — re-run recovery  
- [ ] (Optional) `POST /mcap-logs/{id}/parse` — re-run parsing  


---

*Project by Pettrus Konnoth – FSAE Data Pipeline*
