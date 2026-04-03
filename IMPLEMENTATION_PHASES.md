# Workspace + Session Auth + Realtime Jobs Implementation Plan

This document tracks the full implementation plan for:

- team/workspace data isolation,
- Django session-based authentication,
- realtime job updates over WebSockets (Django Channels + Redis + Celery).

It includes:

- implementation phases,
- exact files touched per phase,
- completion status using checkboxes and strike-through for finished work.

---

## Legend

- [x] ~~Completed item~~
- [ ] Pending item
- [~] In progress item

---

## Phase 0 — Baseline + branch hygiene

### Goals

- Confirm branch merge state and safe base branch.
- Push prior refactor work before auth/workspace changes.

### Status

- [x] ~~Merge refactor branch into `main`~~
- [x] ~~Push merged `main` to remote~~

### Files/areas

- [x] ~~`main` branch history and merge state~~
- [x] ~~Remote sync (`origin/main`)~~

---

## Phase 1 — Session Authentication (Django cookie session)

### Goals

- Replace anonymous API access assumptions with proper session auth.
- Add login/logout/me endpoints and frontend login screen.
- Use cookie session + CSRF (no localStorage password/token storage).

### Status

- [x] ~~Add auth endpoints (`csrf`, `login`, `logout`, `me`)~~
- [x] ~~Wire auth routes under `/api/auth/*`~~
- [x] ~~Enable frontend login page and protected app bootstrap~~
- [x] ~~Switch frontend API client to `credentials: include` + CSRF handling~~
- [x] ~~Add session roundtrip test (`login -> me -> logout`)~~

### Files modified

- [x] ~~`backend/api/auth_views.py`~~
- [x] ~~`backend/backend/urls.py`~~
- [x] ~~`backend/backend/settings.py`~~
- [x] ~~`frontend/lib/mcap/api.ts`~~
- [x] ~~`frontend/app/login/page.tsx`~~
- [x] ~~`frontend/app/page.tsx`~~
- [x] ~~`backend/api/tests.py`~~

### Commit reference

- [x] ~~`ceccd29` — `[backend] add session auth endpoints and cookie-based login flow`~~

---

## Phase 2 — Workspace Data Model + Membership Scoping

### Goals

- Add team/workspace primitives.
- Attach logs and export jobs to a workspace.
- Scope API access by workspace membership.

### Status

- [x] ~~Create `Workspace` model~~
- [x] ~~Create `WorkspaceMember` model with roles~~
- [x] ~~Add `workspace` + `created_by` to `McapLog`~~
- [x] ~~Add `workspace` + `created_by` to `ExportJob`~~
- [x] ~~Create backfill migration for default workspace~~
- [x] ~~Add request workspace resolver helper~~
- [x] ~~Apply workspace-based filtering in logs and export endpoints~~
- [x] ~~Add/adjust tests for workspace membership access rules~~

### Files modified

- [x] ~~`backend/api/models.py`~~
- [x] ~~`backend/api/workspace.py`~~
- [x] ~~`backend/api/permissions.py`~~
- [x] ~~`backend/api/views.py`~~
- [x] ~~`backend/api/views_export.py`~~
- [x] ~~`backend/api/auth_views.py`~~
- [x] ~~`backend/api/tests.py`~~
- [x] ~~`backend/api/migrations/0017_workspace_exportjob_created_by_mcaplog_created_by_and_more.py`~~
- [x] ~~`backend/api/migrations/0018_backfill_default_workspace.py`~~

### Commit reference

- [x] ~~`4d8162e` — `[backend] add workspace models and scope log export access by membership`~~

---

## Phase 3 — Channels Infrastructure (ASGI + Redis channel layer)

### Goals

- Add Django Channels runtime.
- Configure ASGI protocol routing for HTTP + WebSocket.
- Add workspace websocket route and authenticated membership consumer.

### Status

- [x] ~~Add dependencies `channels` and `channels-redis`~~
- [x] ~~Configure `ASGI_APPLICATION` and `CHANNEL_LAYERS`~~
- [x] ~~Switch `asgi.py` to `ProtocolTypeRouter`~~
- [x] ~~Add websocket URL route (`/ws/workspaces/<id>/jobs/`)~~
- [x] ~~Add authenticated + membership-gated websocket consumer~~
- [x] ~~Add backend helper for broadcasting workspace events~~

### Files modified

- [x] ~~`pyproject.toml`~~
- [x] ~~`uv.lock`~~
- [x] ~~`backend/backend/settings.py`~~
- [x] ~~`backend/backend/asgi.py`~~
- [x] ~~`backend/api/routing.py`~~
- [x] ~~`backend/api/consumers.py`~~
- [x] ~~`backend/api/realtime.py`~~

### Notes

- These changes are implemented in working tree and validated locally.
- [x] ~~Committed as backend infrastructure commit (`544bccd`)~~

---

## Phase 4 — Celery -> WebSocket Event Publishing

### Goals

- Emit realtime events from parsing/recovery/export tasks.
- Notify all connected members of a workspace group instantly.

### Status

- [x] ~~Add export lifecycle broadcasts in Celery tasks~~
- [x] ~~Add ingest/parse lifecycle broadcasts in Celery tasks~~
- [x] ~~Standardize event payload schema~~
- [x] ~~Add task-level tests for event emission~~

### Files modified

- [x] ~~`backend/api/jobs/tasks_export.py`~~
- [x] ~~`backend/api/jobs/tasks_ingest.py`~~
- [ ] `backend/api/jobs/tasks_status.py` (optional if centralized)
- [x] ~~`backend/api/realtime.py`~~
- [x] ~~`backend/api/tests.py`~~

### Planned event payload contract

```json
{
  "event_type": "export.status",
  "workspace_id": 1,
  "entity_type": "export_job",
  "entity_id": 42,
  "status": "processing",
  "progress_percent": 50,
  "updated_at": "2026-04-02T00:00:00Z",
  "meta": {
    "completed_items": 3,
    "failed_items": 0,
    "total_items": 6
  }
}
```

---

## Phase 5 — Frontend WebSocket Integration

### Goals

- Subscribe to workspace job stream.
- Update UI status in realtime (reduce polling dependence).

### Status

- [x] ~~Add websocket client util/hook~~
- [x] ~~Resolve active workspace id from authenticated user payload~~
- [x] ~~Connect dashboard to `/ws/workspaces/<id>/jobs/`~~
- [x] ~~Update export/processing UI from incoming events~~
- [x] ~~Keep polling fallback for resilience~~

### Files modified

- [x] ~~`frontend/lib/mcap/ws.ts` (new)~~
- [x] ~~`frontend/lib/mcap/api.ts`~~
- [x] ~~`frontend/app/page.tsx`~~
- [ ] `frontend/components/mcap/modals/DownloadModal.tsx` (optional status details)

---

## Phase 6 — Permission Hardening + Role Enforcement

### Goals

- Enforce workspace roles for sensitive actions.
- Remove any transitional compatibility fallbacks once migration is stable.

### Status

- [ ] Enforce `viewer/editor/admin` policy on mutate endpoints
- [ ] Deny cross-workspace access consistently with 404/403 policy
- [ ] Remove legacy user-field fallback logic if no longer needed

### Planned files

- [ ] `backend/api/permissions.py`
- [ ] `backend/api/views.py`
- [ ] `backend/api/views_export.py`
- [ ] `backend/api/workspace.py`
- [ ] `backend/api/tests.py`

---

## Phase 7 — Deployment/Runtime Wiring

### Goals

- Ensure production websocket support and stable Redis/channel setup.

### Status

- [ ] Verify ASGI server deployment path (`daphne` or `uvicorn`)
- [ ] Verify proxy upgrade headers for WebSockets
- [ ] Confirm Redis availability and separation strategy for Celery/Channels if needed
- [ ] Add env docs for `CHANNEL_REDIS_URL`

### Planned files

- [ ] `compose*.yml` (if websocket runtime/proxy updates required)
- [ ] `README.md`
- [ ] deploy configs/scripts as applicable

---

## Phase 8 — Test Matrix and Verification

### Goals

- Verify correctness across auth, workspace scoping, and realtime updates.

### Status

- [x] ~~Backend auth session roundtrip test present~~
- [x] ~~Workspace export access tests present~~
- [ ] Add websocket consumer membership tests
- [ ] Add Celery event emission tests
- [ ] Add end-to-end two-client workspace realtime smoke test

### Commands currently validated

- [x] ~~`uv run python -m compileall -q backend`~~
- [x] ~~`uv run python backend/manage.py test api.tests.AuthSessionTests api.tests.ExportAuthAccessTests`~~
- [x] ~~`cd frontend && pnpm run lint`~~
- [x] ~~`cd frontend && pnpm run build`~~

---

## Phase 9 — Commit and PR Plan

### Completed commits

- [x] ~~`ceccd29` — session auth backend/frontend flow~~
- [x] ~~`4d8162e` — workspace schema + membership scoping~~

### Next commit (recommended)

- [x] ~~Commit Channels infrastructure files:~~
  - [x] ~~`pyproject.toml`~~
  - [x] ~~`uv.lock`~~
  - [x] ~~`backend/backend/settings.py`~~
  - [x] ~~`backend/backend/asgi.py`~~
  - [x] ~~`backend/api/routing.py`~~
  - [x] ~~`backend/api/consumers.py`~~
  - [x] ~~`backend/api/realtime.py`~~

### Following commit (recommended)

- [x] ~~Commit Celery event publishing integration in task files + tests (`336f9b1`)~~

### Next commit (updated)

- [~] In progress: commit frontend websocket subscription integration.

---

## Current Snapshot (at time of writing)

- [x] ~~Session auth is live~~
- [x] ~~Workspace schema/scoping is live~~
- [x] ~~Channels framework scaffolding is committed~~
- [x] ~~Realtime task event emission wired in backend~~
- [x] ~~Frontend websocket subscription wired~~
