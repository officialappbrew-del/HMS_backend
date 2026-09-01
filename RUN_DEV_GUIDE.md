# Development Server with Auto-Start Celery Worker

The `run_dev` management command automatically starts both the Django development server and the Celery worker, so you don't need separate terminal windows.

## Quick Start

**Simple way to start everything:**
```bash
python manage.py run_dev
```

This will:
- ✅ Start Django development server on `127.0.0.1:8000`
- ✅ Automatically start Celery worker in the background
- ✅ Verify Redis connection before starting
- ✅ Handle graceful shutdown when you press Ctrl+C

## Options

### Run on a different host:port
```bash
python manage.py run_dev 0.0.0.0:8080
```

### Run Django only (without Celery)
```bash
python manage.py run_dev --no-celery
```

## Output Example

When you run the command, you'll see:
```
======================================================================
SMARTCARE HMS - Development Server
======================================================================

✓ Checking Redis connection: redis://red-d9uu0ru417fc7395chkg:6379...
  ✓ Redis connection successful

✓ Starting Django development server on 127.0.0.1:8000
  Press Ctrl+C to stop all services

✓ Starting Celery worker...
  ✓ Celery worker started (PID: 12345)

Watching for file changes with StatReloader
Quit the server with CONTROL-C.
```

## Troubleshooting

### "Celery worker failed to start"
- Make sure Redis is running (check REDIS_URL in .env)
- Verify `CELERY_BROKER_URL` is configured in settings.py
- Run: `pip install celery[redis]`

### "Unknown command: 'run_dev'"
- The command is in the `core` app, which must be in INSTALLED_APPS
- Run: `python manage.py --help` and look for `run_dev`

### "Cannot connect to Redis"
- Check if Redis URL is correct in .env: `REDIS_URL=redis://host:port`
- Test connection: `redis-cli ping`
- For Render Redis, ensure the password is included in the URL if needed

## How It Works

1. **Redis Connection Check**: Verifies Redis is reachable before starting Celery
2. **Celery Worker Launch**: Starts Celery in a subprocess with 2 concurrent workers
3. **Django Server**: Runs in the main process so you can see live reload messages
4. **Graceful Shutdown**: When you press Ctrl+C, both services shut down cleanly

## Login Notifications

With this setup, when a user logs in:
1. Login response returns immediately (non-blocking)
2. Email notification is queued to Redis
3. Celery worker picks it up and sends it in the background
4. Email uses tenant-scoped credentials (or global if admin)

## Production Deployment

For production, use separate processes:
```bash
# Terminal 1: Django application server
gunicorn smartcare_hms.wsgi:application --workers 4

# Terminal 2: Celery worker
celery -A smartcare_hms worker -l info
```
