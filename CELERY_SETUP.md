# Celery Background Processing Setup

This project uses Celery for background processing of MCAP file parsing. This allows file uploads to return immediately while parsing happens asynchronously.

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Start Redis (Message Broker)

Redis is already configured in `compose.yml`. Start it with:

```bash
docker compose up -d redis
```

Or start all services:
```bash
docker compose up -d
```

### 3. Start Celery Worker

In a separate terminal, start the Celery worker:

```bash
cd backend
celery -A backend worker --loglevel=info
```

For development with auto-reload:
```bash
celery -A backend worker --loglevel=info --reload
```

### 4. (Optional) Start Celery Beat (for scheduled tasks)

If you need scheduled tasks:
```bash
celery -A backend beat --loglevel=info
```

### 5. Monitor Celery (Optional)

Install Flower for monitoring:
```bash
uv add flower
celery -A backend flower
```

Then visit `http://localhost:${FLOWER_PORT:-5555}` (or your configured Flower port)

## How It Works

1. **File Upload**: When a file is uploaded via `POST /api/mcap-logs/`, the file is saved and a database record is created with `parse_status="pending"`.

2. **Background Processing**: A Celery task (`parse_mcap_file`) is triggered to parse the file in the background.

3. **Status Updates**: The task updates the database record:
   - `parse_status="processing"` when parsing starts
   - `parse_status="completed"` when parsing succeeds
   - `parse_status="error: <message>"` if parsing fails

4. **Polling**: The frontend can poll the endpoint to check `parse_status` until it's no longer "pending" or "processing".

## Benefits

- ✅ **Fast Response**: API returns immediately after file upload
- ✅ **Scalable**: Can handle multiple files concurrently
- ✅ **Resilient**: Automatic retries on failure (up to 3 retries)
- ✅ **Non-blocking**: Upload 20 files without waiting for each to parse
- ✅ **Timeout Protection**: Tasks timeout after 30 minutes

## Environment Variables

You can override Redis connection:
```bash
export REDIS_HOST=${REDIS_HOST:-localhost}
export REDIS_PORT=${REDIS_PORT:-6379}
export CELERY_BROKER_URL=redis://$REDIS_HOST:$REDIS_PORT/0
export CELERY_RESULT_BACKEND=redis://$REDIS_HOST:$REDIS_PORT/0
```

## Troubleshooting

### Worker not processing tasks
- Check Redis is running: `docker compose ps`
- Check worker logs for errors
- Verify Redis connection: `redis-cli ping`

### Tasks failing
- Check worker logs for detailed error messages
- Tasks automatically retry up to 3 times with exponential backoff
- Check file paths and permissions

### High memory usage
- Adjust `CELERY_WORKER_PREFETCH_MULTIPLIER` in settings.py
- Limit concurrent workers: `celery -A backend worker --concurrency=2`
