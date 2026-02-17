#  MCAP Log API

A Django REST Framework backend for managing and parsing **Formula SAE telemetry logs** recorded in the `.mcap` format.

## Monorepo layout
- `backend/` — Django + Celery API (PostGIS/Redis)
- `frontend/` — Next.js client (pnpm)

### Quick start
- Backend (local): `./scripts/dev_backend_local.sh`
- Celery worker (local, optional): `./scripts/dev_celery_local.sh`
- Frontend: `cd frontend && pnpm install && pnpm run dev`

The service automates:
- Getting MCAP log files from the car’s onboard Pi
- Running `mcap recover` on every uploaded file
- Parsing recovered logs for:
  - Available channels (topics)
  - Start and end timestamps
  - Duration and channel count
  - Rough GPS position (when available)
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
- Optional GPS location (`rough_point`)
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
