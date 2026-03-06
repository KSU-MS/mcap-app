# AGENTS.md

Guide for coding agents working in `mcap_query_backend`.

## Dev environment tips

- Project shape:
  - `backend/`: Django + DRF + Celery + PostGIS
  - `frontend/`: Next.js App Router + TypeScript + pnpm
  - `compose.dev.yml`: Docker Compose local infra (db, redis)
  - `compose.prod.yml`: Docker Compose full stack (db, redis, backend, celery, frontend, nginx)
  - `flake.nix`: reproducible Nix environment/packages
- Local setup (recommended: `uv` + Docker infra, no Nix required):
  - `uv sync`
  - `uv run python backend/manage.py migrate`
  - `uv run python backend/manage.py runserver ${DJANGO_HOST:-127.0.0.1}:${DJANGO_PORT:-8000}`
  - in another shell: `uv run celery -A backend worker --loglevel=info`
  - frontend: `cd frontend && pnpm install && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run dev`
  - infra only: `docker compose -f compose.dev.yml up -d`
- Optional Nix shell (use for reproducible toolchains/builds):
  - `nix develop`
- Docker Compose setup:
  - `cp .env.example .env`
  - local infra: `docker compose -f compose.dev.yml up -d`
  - full stack: `docker compose -f compose.prod.yml up -d --build`
  - Nix-built full stack images + rollout:
    - `nix build .#docker-backend .#docker-celery .#docker-migrate .#docker-frontend`
    - `nix run .#docker-load-images`
    - `docker compose -f compose.nix.yml up -d --force-recreate backend celery migrate`
    - `docker compose -f compose.nix.yml logs -f celery`
  - open `http://localhost:13000`
- Makefile shortcuts:
  - `make dev-up`, `make dev-down`
  - `make prod-up`, `make prod-down`
- Environment variable model (current):
  - Django uses `django-environ` in `backend/backend/settings.py`
  - preferred DB config is `DATABASE_URL`
  - celery uses `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`
  - legacy `POSTGRES_*` vars still work as fallback
- Frontend API base URL:
  - uses `NEXT_PUBLIC_API_BASE_URL` (defaults to `/api`)
- Helpful checks:
  - backend shell sanity: `uv run python -m compileall -q backend`
  - nix checks (optional): `nix flake check`

## Build and lint instructions

- Backend dependency sync:
  - `uv sync`
- Backend migrations:
  - `uv run python backend/manage.py makemigrations`
  - `uv run python backend/manage.py migrate`
- Frontend install/build:
  - `cd frontend && pnpm install`
  - `cd frontend && pnpm run build`
  - `cd frontend && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run start`
- Frontend lint:
  - `cd frontend && pnpm run lint`
- Nix package builds:
  - optional unless you are validating Nix outputs
  - `nix build .#backend`
  - `nix build .#frontend-runner`
- Backend linting note:
  - no repo-level backend linter config (`ruff.toml`, `mypy.ini`) is committed
  - avoid broad formatting/lint rewrites unless explicitly requested

## Testing instructions

- Backend full test suite:
  - `uv run python backend/manage.py test`
- Backend app-only tests:
  - `uv run python backend/manage.py test api`
- Backend single test class:
  - `uv run python backend/manage.py test api.tests.DownloadRequestSerializerTests`
- Backend single test method (preferred for targeted validation):
  - `uv run python backend/manage.py test api.tests.DownloadRequestSerializerTests.test_default_resample_rate_is_applied`
  - `uv run python backend/manage.py test api.tests.McapConverterResampleTests.test_resample_timestamp_groups_returns_fixed_interval`
- Frontend tests:
  - no frontend test runner is currently configured in `frontend/package.json`
  - do not add a new test framework as part of unrelated changes
- Validation expectation:
  - run at least targeted backend tests for touched backend code
  - run `pnpm run lint` and `pnpm run build` for production-impacting frontend changes

## Code style guidelines

- General
  - keep diffs focused and minimal
  - preserve existing formatting in each file
  - avoid unrelated refactors
  - do not rename/move files unless required
- Python (Django/DRF)
  - `PascalCase` for classes, `snake_case` for functions/variables/query params
  - keep imports at top of file; preserve local ordering unless correctness requires change
  - use serializers for request validation/normalization
  - use `serializers.ValidationError` for user input issues
  - return structured DRF `Response` objects with explicit status codes
  - in batch operations, collect per-item failures and continue where safe
  - keep schema changes in `backend/api/migrations/`
  - maintain JSONField list semantics for tags/cars/drivers/event_types/locations
  - use Celery tasks for long-running operations
- TypeScript/React (Next.js)
  - TypeScript strict mode is enabled; avoid `any` unless unavoidable
  - `PascalCase` for components, `camelCase` for vars/functions
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

## PR instructions

- Keep title concise and scoped; recommended format:
  - `[backend] <title>` or `[frontend] <title>` or `[infra] <title>`
- Before commit/PR:
  - run relevant backend test command(s), including single-test command for targeted fixes
  - run `cd frontend && pnpm run lint` for frontend changes
  - run `cd frontend && pnpm run build` for production-impacting frontend changes
- If any validation step cannot be run, state exactly what was skipped and why.

## Cursor/Copilot instructions

- `.cursor/rules/`: not found
- `.cursorrules`: not found
- `.github/copilot-instructions.md`: not found

This `AGENTS.md` is the primary agent instruction file for this repository.
