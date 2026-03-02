#!/usr/bin/env bash
# Start or stop Postgres (16+PostGIS) and Redis from Nix. Run from repo root or inside nix develop.
# Data lives under .nix-data/ by default (set NIX_DATA_DIR to override).
set -euo pipefail

# Avoid invalid global locale overrides breaking redis-server startup.
unset LC_ALL || true
export LANG="${LANG:-C.UTF-8}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NIX_DATA_DIR="${NIX_DATA_DIR:-$ROOT/.nix-data}"
PGDATA="$NIX_DATA_DIR/postgres"
REDIS_DIR="$NIX_DATA_DIR/redis"
REDIS_PIDFILE="$REDIS_DIR/redis.pid"
REDIS_LOGFILE="$REDIS_DIR/redis.log"
POSTGRES_PORT="${POSTGRES_PORT:-5433}"
POSTGRES_SOCKET_DIR="${POSTGRES_SOCKET_DIR:-/tmp}"
REDIS_PORT="${REDIS_PORT:-6379}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-mcap_query_db}"
RECONCILE_MAP_PREVIEWS="${RECONCILE_MAP_PREVIEWS:-1}"
RECONCILE_MAP_PREVIEWS_LIMIT="${RECONCILE_MAP_PREVIEWS_LIMIT:-0}"

command -v pg_ctl >/dev/null 2>&1 || { echo "pg_ctl not on PATH. Run this script inside 'nix develop'."; exit 1; }
command -v redis-server >/dev/null 2>&1 || { echo "redis-server not on PATH. Run this script inside 'nix develop'."; exit 1; }

case "${1:-start}" in
  start)
    mkdir -p "$NIX_DATA_DIR" "$REDIS_DIR" "$POSTGRES_SOCKET_DIR"

    # Postgres: init if needed, then start
    if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
      echo "Initializing Postgres data in $PGDATA ..."
      initdb -D "$PGDATA" -U "$POSTGRES_USER"
    fi
    if ! pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
      echo "Starting Postgres on port $POSTGRES_PORT ..."
      pg_ctl -D "$PGDATA" -o "-p $POSTGRES_PORT -k $POSTGRES_SOCKET_DIR" -l "$PGDATA/logfile" start
      sleep 2
      createdb -h localhost -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB" 2>/dev/null || true
    else
      echo "Postgres already running (port $POSTGRES_PORT)."
    fi

    # Redis: start if not already listening
    if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "Starting Redis on port $REDIS_PORT ..."
      redis-server \
        --port "$REDIS_PORT" \
        --bind 127.0.0.1 \
        --dir "$REDIS_DIR" \
        --pidfile "$REDIS_PIDFILE" \
        --logfile "$REDIS_LOGFILE" \
        --daemonize yes
      sleep 1
      if ! redis-cli -h 127.0.0.1 -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        echo "Redis failed to start on port $REDIS_PORT. See $REDIS_LOGFILE" >&2
        exit 1
      fi
    else
      echo "Redis already running (port $REDIS_PORT)."
    fi

    echo "Services ready. Postgres: localhost:$POSTGRES_PORT ($POSTGRES_DB) | Redis: localhost:$REDIS_PORT"

    if [[ "$RECONCILE_MAP_PREVIEWS" == "1" ]]; then
      if [[ -f "$ROOT/backend/manage.py" ]]; then
        echo "Reconciling map previews (sync, idempotent) ..."
        set +e
        if command -v nix >/dev/null 2>&1; then
          reconcile_cmd=(nix develop -c python "$ROOT/backend/manage.py" generate_map_previews --sync)
        else
          reconcile_cmd=(python "$ROOT/backend/manage.py" generate_map_previews --sync)
        fi
        if [[ "$RECONCILE_MAP_PREVIEWS_LIMIT" =~ ^[0-9]+$ ]] && [[ "$RECONCILE_MAP_PREVIEWS_LIMIT" -gt 0 ]]; then
          reconcile_cmd+=(--limit "$RECONCILE_MAP_PREVIEWS_LIMIT")
        fi
        "${reconcile_cmd[@]}"
        rc=$?
        set -e
        if [[ $rc -ne 0 ]]; then
          echo "Map preview reconciliation failed (exit $rc)."
          echo "You can retry manually: nix develop -c python backend/manage.py generate_map_previews --sync"
          echo "Or disable auto-reconcile with: RECONCILE_MAP_PREVIEWS=0 ./scripts/start-nix-services.sh start"
        fi
      else
        echo "Skipping map preview reconciliation: backend/manage.py not found."
      fi
    fi
    ;;
  stop)
    echo "Stopping Postgres and Redis ..."
    redis-cli -p "$REDIS_PORT" shutdown 2>/dev/null || true
    pg_ctl -D "$PGDATA" stop -m fast 2>/dev/null || true
    echo "Stopped."
    ;;
  status)
    if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
      echo "Postgres: running (port $POSTGRES_PORT)"
    else
      echo "Postgres: stopped"
    fi
    if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "Redis: running (port $REDIS_PORT)"
    else
      echo "Redis: stopped"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|status}" >&2
    exit 1
    ;;
esac
