#!/usr/bin/env bash
# Migrate data from Docker Postgres (compose.yml) to Nix Postgres (.nix-data).
# Prerequisites:
#   - Docker Compose db running: docker compose up -d db
#   - Nix Postgres running: ./scripts/start-nix-services.sh start
#   - Run from repo root, ideally inside nix develop (for pg_dump/dropdb/createdb/psql).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
NIX_DATA_DIR="${NIX_DATA_DIR:-$ROOT/.nix-data}"
BACKUP_FILE="${NIX_DATA_DIR}/docker-mcap_query_db-backup.sql"
POSTGRES_PORT="${POSTGRES_PORT:-5433}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-mcap_query_db}"

echo "1. Dumping from Docker Postgres (service 'db')..."
docker compose exec -T db pg_dump -U postgres "$POSTGRES_DB" > "$BACKUP_FILE"
echo "   Dumped to $BACKUP_FILE"

echo "2. Restoring into Nix Postgres (localhost:$POSTGRES_PORT)..."
command -v dropdb >/dev/null 2>&1 || { echo "dropdb not on PATH. Run this script inside 'nix develop'."; exit 1; }
dropdb -h localhost -p "$POSTGRES_PORT" -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
createdb -h localhost -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB"
psql -h localhost -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB" < "$BACKUP_FILE"
echo "   Restore complete."

echo "Done. Nix Postgres now has the data from Docker."
