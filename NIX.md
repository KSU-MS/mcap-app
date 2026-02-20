# Nix dev shell (production-like environment)

This project has a Nix flake so you can run the **same stack** you’ll use on a NixOS server: Python 3.13, GDAL/GEOS, **PostgreSQL 16 with PostGIS**, Redis, `uv`, and Node — all from Nix. No Docker required for DB or Redis.

## Prerequisites

- [Nix](https://nixos.org/download/) with flakes enabled (e.g. `nix --version` ≥ 2.4).
- If Nix reports “path is not tracked by Git”, add the flake so Git tracks it:  
  `git add flake.nix NIX.md` (and `flake.lock` after the first `nix develop`).

## Enter the dev shell

```bash
nix develop
```

Inside the shell you get:

- **Python 3.13** and **uv**
- **GDAL** and **GEOS** (GeoDjango) from Nix, with `GDAL_LIBRARY_PATH` and `GEOS_LIBRARY_PATH` set
- **PostgreSQL 16 with PostGIS** (same as `compose.yml` / production)
- **Redis**
- **Node.js 22** for the frontend

Python dependencies are still managed by **uv**: run `uv sync` in the repo root or in `backend/`.  
The shell also sets `POSTGRES_*` and `CELERY_*` env vars to match `backend/backend/settings.py`.

## Running Postgres and Redis from Nix (recommended)

From the repo root, **inside** `nix develop`:

```bash
./scripts/start-nix-services.sh start
```

This will:

- Create a data directory `.nix-data/` (ignored by git) if needed
- Initialize Postgres on first run, then start it on **port 5433**
- Create the database `mcap_query_db` if it doesn’t exist
- Start Redis on **port 6379**

Then:

- **Stop** services: `./scripts/start-nix-services.sh stop`
- **Status**: `./scripts/start-nix-services.sh status`

## Typical workflow on macOS (full Nix stack)

1. **Enter the Nix shell and start DB + Redis:**

   ```bash
   nix develop
   ./scripts/start-nix-services.sh start
   ```

2. **Run migrations and start the backend:**

   From repo root, inside `nix develop`:
   ```bash
   uv sync
   uv run python backend/manage.py migrate
   uv run python backend/manage.py runserver
   ```

3. **In another terminal** (Celery):

   ```bash
   nix develop
   uv run celery -A backend worker --loglevel=info
   ```

4. **Frontend** (optional):

   ```bash
   cd frontend && pnpm install && pnpm run dev
   ```

You can still use **Docker** for Postgres/Redis if you prefer: `docker compose up -d db redis`. The app env (Python, GDAL, etc.) is the same either way.

### Migrating data from Docker Postgres to Nix Postgres

If you have data in Docker Postgres and want it in Nix Postgres:

1. Start Docker Postgres: `docker compose up -d db`
2. Start Nix Postgres: `./scripts/start-nix-services.sh start`
3. From repo root (inside `nix develop`): `./scripts/migrate-docker-postgres-to-nix.sh`

The script dumps `mcap_query_db` from the Docker container and restores it into the Nix Postgres instance (replacing any existing data there). The backup is written to `.nix-data/docker-mcap_query_db-backup.sql`.

## Why use this

- **Same stack as NixOS server**: Same Postgres+PostGIS, Redis, Python, and libs you’ll use in production.
- **No Docker for DB/Redis**: Run everything from the flake; data lives in `.nix-data/`.
- **No Homebrew for GIS**: GDAL/GEOS come from Nix.
- **Reproducible**: Pin with `flake.lock` for a deterministic environment.

## Lock the flake (optional)

To pin Nixpkgs and get a reproducible shell:

```bash
nix flake lock
```

Commit `flake.lock` so others (and CI) get the same environment.

## Linux (e.g. NixOS server)

The same flake works on `x86_64-linux`. On a NixOS server you’d typically:

- Use this flake (or a NixOS module that wraps it) to define the app environment.
- Enable `services.postgresql` (with PostGIS) and `services.redis`, and run Django + Celery as systemd services — same versions, no Docker.
