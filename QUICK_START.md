# Quick Start Guide

## 🚀 For Local Development (Windows)

### Your Preferred Setup
```bash
# Navigate to the backend directory
cd C:\Users\HP\Desktop\HMS\HMS_backend

# Start everything automatically
python manage.py run_dev
```

**That's it!** This starts:
- ✅ Django on `127.0.0.1:8000` (your preferred port)
- ✅ Celery worker in background
- ✅ Both shutdown together with Ctrl+C

---

## 🌐 For Render Production

**You don't need to do anything!** 

Render is already configured via `render.yaml` to automatically:
- ✅ Start web service (gunicorn) on port 8000
- ✅ Start worker service (Celery) as separate process
- ✅ Connect to Redis (auto-provisioned)
- ✅ Connect to Database (auto-provisioned)

**How login notifications work on Render:**
```
User logs in → Django returns immediately → Email queued to Redis → 
Celery worker picks it up → Email sent asynchronously
```

All automatic, no manual intervention needed.

---

## 🎯 The Full Story

### Local Development
| Command | What It Does |
|---------|-------------|
| `python manage.py run_dev` | Starts Django + Celery on localhost:8000 (RECOMMENDED) |
| `python manage.py run_dev 127.0.0.1:8000` | Explicit localhost:8000 |
| `python manage.py run_dev --no-celery` | Django only, no Celery |

### Render Production
| Process | What It Does |
|---------|-------------|
| Web Service (gunicorn) | Handles HTTP requests, returns responses fast |
| Worker Service (Celery) | Processes background tasks (emails, notifications, etc.) |

---

## ✅ What's Working Right Now

✅ **Login notification feature**: When users log in, they get email notifications  
✅ **Non-blocking**: Login returns immediately (doesn't wait for email)  
✅ **Tenant-aware**: Uses tenant's email credentials (or global for admins)  
✅ **Local auto-start**: `python manage.py run_dev` starts both services  
✅ **Render auto-start**: render.yaml defines both web + worker services  
✅ **Render Redis**: Connected to `redis://red-d9uu0ru417fc7395chkg:6379`

---

## 📝 Key Files

- **Local command**: `core/management/commands/run_dev.py`
- **Email task**: `users/tasks.py` → `send_login_notification_email_task()`
- **Render config**: `render.yaml`
- **Documentation**: 
  - `RUN_DEV_GUIDE.md` - Local development details
  - `DEPLOYMENT_GUIDE.md` - Both environments guide

---

## 🔧 Need Help?

**Local development issue?**
```bash
cd C:\Users\HP\Desktop\HMS\HMS_backend
python manage.py run_dev --help
```

**Render issue?**
- Check: https://dashboard.render.com → Logs
- Worker service (smartcare-hms-celery) must be "Running"
- Web service (smartcare-hms) must be "Running"

**Redis connection?**
- Local: Uses Render's Redis (can reach from your machine)
- Render: Uses Render's provisioned Redis service
