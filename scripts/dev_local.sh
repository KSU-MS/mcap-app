#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Avoid Docker env leaking into local runs
unset VIRTUAL_ENV || true
unset PYTHONHOME || true

# Parse arguments
SERVICE="${1:-both}"

# Common environment variables
export DJANGO_HOST=${DJANGO_HOST:-127.0.0.1}
export DJANGO_PORT=${DJANGO_PORT:-8000}
export REDIS_HOST=${REDIS_HOST:-localhost}
export REDIS_PORT=${REDIS_PORT:-6379}
export MEDIA_ROOT=${MEDIA_ROOT:-/Users/pettruskonnoth/Documents}

if [[ -z "${CELERY_BROKER_URL:-}" ]]; then
  export CELERY_BROKER_URL="redis://${REDIS_HOST}:${REDIS_PORT}/0"
fi
if [[ -z "${CELERY_RESULT_BACKEND:-}" ]]; then
  export CELERY_RESULT_BACKEND="redis://${REDIS_HOST}:${REDIS_PORT}/0"
fi

# Sync dependencies
uv sync

# Some environments (notably macOS + uv) may create only .venv/bin/python3.
# Django's autoreloader may try to respawn using .venv/bin/python, so ensure it exists.
if [[ ! -x "$ROOT_DIR/.venv/bin/python" && -x "$ROOT_DIR/.venv/bin/python3" ]]; then
  ln -sf "python3" "$ROOT_DIR/.venv/bin/python"
fi

# Function to run backend
run_backend() {
  echo "Starting Django backend..."
  cd "$ROOT_DIR/backend"
  if [[ "${RELOAD:-0}" == "1" ]]; then
    uv run python manage.py runserver "$DJANGO_HOST:$DJANGO_PORT"
  else
    uv run python manage.py runserver "$DJANGO_HOST:$DJANGO_PORT" --noreload
  fi
}

# Function to run celery
run_celery() {
  echo "Starting Celery worker..."
  cd "$ROOT_DIR/backend"
  uv run celery -A backend worker --loglevel=info
}

# Run based on argument
case "$SERVICE" in
  backend)
    run_backend
    ;;
  celery)
    run_celery
    ;;
  both)
    echo "Starting both backend and celery in parallel..."
    # Run backend in background
    run_backend &
    BACKEND_PID=$!
    
    # Run celery in foreground (so Ctrl+C kills both)
    run_celery &
    CELERY_PID=$!
    
    # Wait for either process to exit
    wait -n
    
    # If we get here, one process exited - kill both
    kill $BACKEND_PID $CELERY_PID 2>/dev/null || true
    wait
    ;;
  *)
    echo "Usage: $0 [backend|celery|both]"
    echo ""
    echo "  backend  - Run only Django backend"
    echo "  celery   - Run only Celery worker"
    echo "  both     - Run both in parallel (default)"
    echo ""
    echo "Environment variables:"
    echo "  DJANGO_HOST         - Backend host (default: 127.0.0.1)"
    echo "  DJANGO_PORT         - Backend port (default: 8000)"
    echo "  REDIS_HOST          - Redis host (default: localhost)"
    echo "  REDIS_PORT          - Redis port (default: 6379)"
    echo "  RELOAD=1           - Enable Django autoreload (default: disabled)"
    echo "  CELERY_BROKER_URL  - Redis broker URL (default: redis://$REDIS_HOST:$REDIS_PORT/0)"
    echo "  MEDIA_ROOT         - Media files directory (default: /Users/pettruskonnoth/Documents)"
    exit 1
    ;;
esac
