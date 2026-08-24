"""Lightweight, uncached health-check view.

Wired into both the tenant schema URLconf (`smartcare_hms.urls`) and the public
schema URLconf (`smartcare_hms.urls_public`) so it responds on the platform
landing domain (where Render hits `healthCheckPath: /health/`) and on tenant
subdomains.

It is already excluded from the rate-limit and request-logging middleware
(`smartcare_hms/throttling.py`, `smartcare_hms/logging_middleware.py`), so it
stays cheap and cannot 429 under load.
"""
import logging

from django.http import JsonResponse
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)


def _check_database():
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - any failure means DB is unreachable
        logger.warning("Health check database probe failed: %s", exc)
        return "fail"


def _check_redis():
    try:
        from django_redis import get_redis_connection

        connection = get_redis_connection("default")
        connection.ping()
        return "ok"
    except Exception:  # noqa: BLE001 - Redis is optional in dev
        return "unavailable"


@never_cache
def health_check(request):
    database_status = _check_database()
    redis_status = _check_redis()

    healthy = database_status == "ok"
    status_code = 200 if healthy else 503

    return JsonResponse(
        {
            "status": "ok" if healthy else "degraded",
            "checks": {
                "database": database_status,
                "redis": redis_status,
            },
        },
        status=status_code,
    )
