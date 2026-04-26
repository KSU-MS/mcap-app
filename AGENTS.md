# AGENTS.md

Guide for coding agents working in `mcap_query_backend`.

## Dev environment tips

- Project shape:
  - `backend/`: Django + DRF + PostGIS API
  - `go_worker/`: Go workers (`job_runner`, `mcap_fanout_worker`, `export_convert_worker`)
  - `frontend/`: Next.js App Router + TypeScript + pnpm
  - `compose.yml`: local Docker infra (Postgres/PostGIS only)
- Local setup (host-run apps + Docker DB):
  - `cp .env.example .env`
  - `docker compose up -d`
  - `uv sync`
  - `uv run python backend/manage.py migrate`
  - backend API: `cd backend && uv run daphne -b 127.0.0.1 -p 8000 backend.asgi:application`
  - frontend: `cd frontend && pnpm install && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run dev`
  - Go worker (separate shell):
    - `cd go_worker && go build -o mcap_fanout_worker ./cmd/mcap_fanout_worker`
    - `cd go_worker && go build -o export_convert_worker ./cmd/export_convert_worker`
    - `cd go_worker && go build -o job_runner ./cmd/job_runner`
    - `DATABASE_URL=... MCAP_FANOUT_GO_CMD=./mcap_fanout_worker MCAP_EXPORT_CMD=./export_convert_worker ./job_runner`
- Background jobs:
  - Python `process_jobs` execution path is deprecated.
  - `uv run python backend/manage.py process_jobs` only prints a deprecation warning.
  - Use Go `job_runner` for ingest/export/map preview jobs.
- Infra lifecycle:
  - up: `docker compose up -d`
  - down: `docker compose down`

## Build and lint instructions

- Backend dependency sync: `uv sync`
- Backend migrations:
  - `uv run python backend/manage.py makemigrations`
  - `uv run python backend/manage.py migrate`
- Backend sanity check: `uv run python -m compileall -q backend`
- Frontend install/build:
  - `cd frontend && pnpm install`
  - `cd frontend && pnpm run build`
  - `cd frontend && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run start`
- Frontend lint: `cd frontend && pnpm run lint`
- Backend linting note:
  - no repo-level backend linter config (`ruff.toml`, `mypy.ini`) is committed
  - avoid broad formatting/lint rewrites unless explicitly requested

## Testing instructions

- Backend full suite: `uv run python backend/manage.py test`
- Backend app-only: `uv run python backend/manage.py test api`
- Useful targeted tests:
  - `uv run python backend/manage.py test api.tests.DownloadRequestSerializerTests`
  - `uv run python backend/manage.py test api.tests.ExportCreateRequestSerializerTests`
  - `uv run python backend/manage.py test api.tests.ExportAuthAccessTests`
- Frontend tests:
  - no frontend test runner is configured in `frontend/package.json`
  - do not add a new test framework as part of unrelated changes
- Validation expectation:
  - run at least targeted backend tests for touched backend code
  - run `pnpm run lint` and `pnpm run build` for production-impacting frontend changes

## Code style guidelines

- General:
  - keep diffs focused and minimal
  - preserve existing formatting in each file
  - avoid unrelated refactors
  - do not rename/move files unless required
- Python (Django/DRF):
  - `PascalCase` classes, `snake_case` functions/variables/query params
  - keep imports at top of file; preserve local ordering unless correctness requires change
  - use serializers for request validation/normalization
  - use `serializers.ValidationError` for user input issues
  - return structured DRF `Response` objects with explicit status codes
  - in batch operations, collect per-item failures and continue where safe
  - keep schema changes in `backend/api/migrations/`
  - maintain JSONField list semantics for tags/cars/drivers/event_types/locations
  - use DB enqueue helpers; long-running background processing is handled by Go `job_runner`
- TypeScript/React (Next.js):
  - TypeScript strict mode is enabled; avoid `any` unless unavoidable
  - `PascalCase` components, `camelCase` vars/functions
  - preserve backend-required snake_case payload keys where needed
  - prefer `@/` path aliases for internal imports
  - use `import type` when practical
  - keep hooks at top level and satisfy dependency rules
  - centralize API calls in `frontend/lib/mcap/api.ts`
  - keep explicit loading/error UI states

## API/runtime notes

- API routes are under `/api/` in `backend/backend/urls.py`
- docs endpoints:
  - `/swagger/`
  - `/redoc/`
- Django DB config:
  - `DATABASE_URL` is primary
  - DB engine is PostGIS (`django.contrib.gis.db.backends.postgis`)
- Frontend API base URL:
  - `NEXT_PUBLIC_API_BASE_URL` (defaults to `/api`)

## PR instructions

- Keep title concise and scoped; recommended format:
  - `[backend] <title>` or `[frontend] <title>` or `[infra] <title>`
- Before commit/PR:
  - run relevant backend test command(s)
  - run `cd frontend && pnpm run lint` for frontend changes
  - run `cd frontend && pnpm run build` for production-impacting frontend changes
- If any validation step cannot be run, state exactly what was skipped and why.

## Cursor/Copilot instructions

- `.cursor/rules/`: not found
- `.cursorrules`: not found
- `.github/copilot-instructions.md`: not found

This `AGENTS.md` is the primary agent instruction file for this repository.
