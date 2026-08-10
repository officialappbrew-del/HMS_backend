FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=on

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Create non-root user
RUN adduser --disabled-password --gecos '' django-user \
    && chown -R django-user:django-user /app
USER django-user

# Run the application
# - Use gthread worker class so each worker can handle many concurrent connections
# - Default to 2 workers + 4 threads per worker (tune via GUNICORN_WORKERS/GUNICORN_THREADS)
# - Run as a non-root user (django-user) for security
# - Bind to a unix socket via --bind so gunicorn manages lifecycle cleanly
CMD ["sh", "-c", "gunicorn smartcare_hms.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-4} --worker-class gthread --timeout 120 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile -"]
