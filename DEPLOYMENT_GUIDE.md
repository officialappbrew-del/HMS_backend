# Deployment Guide: Local Development vs. Render Production

## 🚀 Local Development (Windows)

### Quick Start (Preferred)
```bash
cd HMS_backend
python manage.py run_dev
```

**This automatically:**
- Starts Django dev server on `127.0.0.1:8000`
- Starts Celery worker in background
- Verifies Redis connection
- Handles graceful shutdown on Ctrl+C

### Alternative Commands

**Run on different port:**
```bash
python manage.py run_dev 127.0.0.1:8080
```

**Django only (no Celery):**
```bash
python manage.py run_dev --no-celery
```

**Manual setup (if run_dev not available):**
```bash
# Terminal 1: Django dev server
python manage.py runserver 127.0.0.1:8000

# Terminal 2: Celery worker (in separate venv terminal)
celery -A smartcare_hms worker -l info
```

---

## 🌐 Render Production Deployment

### Architecture

Render automatically runs **two separate services**:

1. **Web Service** (smartcare-hms)
   - Runs: `gunicorn smartcare_hms.wsgi:application`
   - Port: 8000 (assigned by Render)
   - Purpose: Django application server
   - Replicas: Configurable (default: 1)

2. **Worker Service** (smartcare-hms-celery)
   - Runs: `celery -A smartcare_hms worker --loglevel=info`
   - Purpose: Processes background tasks (login notifications, emails, etc.)
   - Replicas: Configurable (default: 1)

### Configuration File

**File:** `render.yaml` (in HMS_backend root)

```yaml
services:
  - type: web
    name: smartcare-hms
    # ... web service config ...
    startCommand: gunicorn smartcare_hms.wsgi:application ...

  - type: worker
    name: smartcare-hms-celery
    # ... worker service config ...
    startCommand: celery -A smartcare_hms worker --loglevel=info
```

### Automatic Features on Render

✅ **Celery Worker Auto-Start**: No manual intervention needed  
✅ **Separate Processes**: Web and worker run independently  
✅ **Redis Connection**: Automatically provisioned and connected  
✅ **Database Connection**: Automatically provisioned and connected  
✅ **Environment Variables**: Automatically injected from services  
✅ **Health Monitoring**: Render monitors both services  

### Login Notification Flow on Render

```
1. User logs in
   ↓
2. Web service (gunicorn) returns response immediately (non-blocking)
   ↓
3. Notification queued to Redis (render's managed Redis service)
   ↓
4. Worker service (Celery) picks up task from queue
   ↓
5. Celery sends email in background (tenant or global credentials)
   ↓
6. Email delivered asynchronously
```

### Monitoring on Render

**Check web service logs:**
```
https://dashboard.render.com → select smartcare-hms → Logs tab
```

**Check worker service logs:**
```
https://dashboard.render.com → select smartcare-hms-celery → Logs tab
```

### Scaling on Render

To increase Celery workers (recommended for production):

1. Go to Render Dashboard
2. Select `smartcare-hms-celery` service
3. Settings → Instances → increase count
4. Render will automatically start additional worker processes

---

## 🔄 Environment Variables

### Local Development (.env file)
```
DEBUG=True
DATABASE_MODE=local
LOCAL_DATABASE_URL=postgresql://postgres:pluralsight@localhost:5432/HMS_DB
REDIS_URL=redis://red-d9uu0ru417fc7395chkg:6379
CELERY_BROKER_URL=redis://red-d9uu0ru417fc7395chkg:6379
```

### Render Production (render.yaml)
```yaml
envVars:
  - key: REDIS_URL
    fromService:
      name: smartcare_hms_redis  # Auto-provisioned by Render
  - key: DATABASE_URL
    fromDatabase:
      name: smartcare_hms_db     # Auto-provisioned by Render
```

---

## ✅ Verification Checklist

### Local Development
- [ ] `python manage.py run_dev` starts without errors
- [ ] See "✓ Django development server started"
- [ ] See "✓ Celery worker started"
- [ ] Can login at `http://127.0.0.1:8000`
- [ ] Login notifications appear in logs
- [ ] Ctrl+C stops both services gracefully

### Render Production
- [ ] `smartcare-hms` web service shows "Running"
- [ ] `smartcare-hms-celery` worker service shows "Running"
- [ ] No errors in either service's logs
- [ ] Health check endpoint returns 200 OK
- [ ] Can login at production URL
- [ ] Check worker logs for email send confirmations

---

## 🐛 Troubleshooting

### Local: "Unknown command: 'run_dev'"
```bash
# The command is in the core app
# Verify core is in INSTALLED_APPS in settings.py
python manage.py help | grep run_dev
```

### Local: "Cannot connect to Redis"
```bash
# Check REDIS_URL in .env
# Test Redis: redis-cli ping
# Verify Render Redis URL is accessible from your machine
```

### Local: "Celery worker failed to start"
```bash
# Install dependencies
pip install celery[redis]

# Check requirements.txt includes celery and redis
grep -i celery requirements.txt
grep -i redis requirements.txt
```

### Render: Worker service not starting
- Check worker service logs in Render dashboard
- Verify `CELERY_BROKER_URL` is set to Redis service URL
- Ensure Redis service is provisioned and running
- Check `render.yaml` syntax

### Render: Emails not sending
- Check worker service logs for task execution
- Verify `REDIS_URL` is correct in both services
- Check email configuration in Django settings
- Look for tenant email configuration issues

---

## 🎯 Summary

| Aspect | Local | Render |
|--------|-------|--------|
| **Start Method** | `python manage.py run_dev` | Automatic (render.yaml) |
| **Django Port** | 8000 | 8000 (assigned by Render) |
| **Celery** | Background thread | Separate worker service |
| **Redis** | Remote (Render's instance) | Auto-provisioned service |
| **Database** | Local PostgreSQL | Render's managed database |
| **Scaling** | Single process | Multiple replicas per service |

Both environments now have **automatic** Celery worker startup! 🎉
