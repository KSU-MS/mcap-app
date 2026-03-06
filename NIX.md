# Nix dev shell (optional)

This project has a Nix flake so you can run a reproducible toolchain (Python 3.13, GDAL/GEOS, `uv`, Node, Postgres, Redis) from Nix.

Important: Nix is optional for this repo. The default day-to-day workflow is `uv` + Docker Compose.

## Prerequisites

- [Nix](https://nixos.org/download/) with flakes enabled (e.g. `nix --version` ≥ 2.4).
- If Nix reports “path is not tracked by Git”, add the flake so Git tracks it:  
  `git add flake.nix NIX.md` (and `flake.lock` after the first `nix develop`).

## Default workflow (no Nix required)

Use this on macOS/Linux for normal local development:

```bash
cp .env.example .env
make dev-up
uv sync
uv run python backend/manage.py migrate
uv run python backend/manage.py runserver ${DJANGO_HOST:-127.0.0.1}:${DJANGO_PORT:-8000}
```

In another terminal:

```bash
uv run celery -A backend worker --loglevel=info
```

And for frontend:

```bash
cd frontend && pnpm install && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run dev
```

## Enter the Nix shell (optional)

```bash
nix develop
```

Inside the shell you get:

- **Python 3.13** and **uv**
- **GDAL** and **GEOS** (GeoDjango) from Nix, with `GDAL_LIBRARY_PATH` and `GEOS_LIBRARY_PATH` set
- **PostgreSQL 16 with PostGIS** (same database family as production)
- **Redis**
- **Node.js 22** for the frontend

Python dependencies are still managed by **uv**.

## Typical Nix-assisted workflow

Use this when you specifically want Nix-managed binaries/libs:

1. Enter shell:

   ```bash
   nix develop
   ```

2. Start local infra with Docker Compose (still recommended):

   ```bash
   docker compose -f compose.dev.yml up -d
   ```

3. Run backend:

   ```bash
   uv sync
   uv run python backend/manage.py migrate
   uv run python backend/manage.py runserver ${DJANGO_HOST:-127.0.0.1}:${DJANGO_PORT:-8000}
   ```

4. In another terminal, run celery:

   ```bash
   nix develop
   uv run celery -A backend worker --loglevel=info
   ```

5. Frontend:

   ```bash
   cd frontend && pnpm install && FRONTEND_PORT=${FRONTEND_PORT:-3000} pnpm run dev
   ```

### Port environment variables

- `POSTGRES_HOST_PORT` (dev compose host port, default `5433`)
- `REDIS_HOST_PORT` (dev compose host port, default `6379`)
- `DJANGO_HOST` / `DJANGO_PORT` (backend bind host/port, defaults `127.0.0.1` / `8000`)
- `FRONTEND_PORT` (Next.js dev/start port, default `3000`)

## Why use this

- **Same stack as NixOS server**: Same Postgres+PostGIS, Redis, Python, and libs you’ll use in production.
- **Optional reproducibility**: Pin toolchains and libraries with `flake.lock`.
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

## Nix-built Docker images (no Dockerfile)

This repo also exposes Docker image artifacts built directly from flake outputs for app services:

- `docker-backend` (`mcap-backend:nix`)
- `docker-celery` (`mcap-celery:nix`)
- `docker-migrate` (`mcap-migrate:nix`)
- `docker-frontend` (`mcap-frontend:nix`)

Use a Linux builder/runner for these image builds (container payloads must be Linux).

```bash
nix build .#packages.x86_64-linux.docker-backend \
  .#packages.x86_64-linux.docker-celery \
  .#packages.x86_64-linux.docker-migrate \
  .#packages.x86_64-linux.docker-frontend
nix run .#packages.x86_64-linux.docker-load-images
docker compose -f compose.nix.yml up -d
```

`compose.nix.yml` keeps all service-to-service traffic on Docker internal networking and only exposes nginx on `${NGINX_HOST_PORT:-13000}`.
