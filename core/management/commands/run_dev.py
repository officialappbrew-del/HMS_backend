"""
Management command to run Django development server with Celery worker.
This allows development without needing to manually start a separate Celery worker process.

Usage:
    python manage.py run_dev              # Run with defaults (localhost:8000)
    python manage.py run_dev 0.0.0.0:8080 # Run on different host:port
"""

import os
import sys
import subprocess
import signal
import time
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Run Django development server with Celery worker'

    def add_arguments(self, parser):
        parser.add_argument(
            'addrport',
            nargs='?',
            default='127.0.0.1:8000',
            help='Optional host:port for Django development server (default: 127.0.0.1:8000)',
        )
        parser.add_argument(
            '--no-celery',
            action='store_true',
            help='Run Django server only, without Celery worker',
        )

    def handle(self, *args, **options):
        """Start Django development server and Celery worker."""
        addrport = options['addrport']
        no_celery = options.get('no_celery', False)

        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('SMARTCARE HMS - Development Server'))
        self.stdout.write(self.style.SUCCESS('=' * 70))

        if not settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  WARNING: DEBUG mode is OFF. Development server should run with DEBUG=True'
                )
            )

        # Verify Redis connection is available if Celery will be used
        if not no_celery:
            self._verify_redis_connection()

        # Start Django development server
        self.stdout.write(self.style.SUCCESS(f'\n✓ Starting Django development server on {addrport}'))
        self.stdout.write(self.style.WARNING('  Press Ctrl+C to stop all services'))
        self.stdout.write('')

        if no_celery:
            # Run Django server only
            self._run_django_server(addrport)
        else:
            # Run Django server with Celery worker
            self._run_django_with_celery(addrport)

    def _verify_redis_connection(self):
        """Check if Redis is accessible before starting Celery (non-blocking, continues even if unavailable)."""
        try:
            import redis
            redis_url = settings.CELERY_BROKER_URL
            
            if not redis_url or redis_url.startswith('memory://') or redis_url == 'django-db':
                self.stdout.write(
                    self.style.WARNING(
                        '⚠️  Redis not configured. Celery will use in-memory broker (not recommended for production).'
                    )
                )
                return

            self.stdout.write(f'  Checking Redis connection: {redis_url}...')
            
            # Extract host and port from Redis URL
            # Format: redis://[user:password@]host[:port][/db]
            try:
                r = redis.from_url(redis_url, socket_connect_timeout=5)
                r.ping()
                self.stdout.write(self.style.SUCCESS('  ✓ Redis connection successful'))
                return True
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n⚠️  WARNING: Cannot connect to Redis at {redis_url}'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        '  Celery worker will attempt to start, but may fail if Redis is unreachable.'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        '  Django will continue running. Use --no-celery if you want Django only.\n'
                    )
                )
                return False

        except ImportError:
            self.stdout.write(
                self.style.WARNING('  ⚠️  redis-py not installed. Skipping Redis health check.')
            )
            return False

    def _run_django_with_celery(self, addrport):
        """Run Django dev server and Celery worker in separate processes."""
        # Start Celery worker in a subprocess
        celery_process = self._start_celery_worker()

        try:
            # Run Django development server in main process
            self._run_django_server(addrport)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\nShutting down services...'))
        finally:
            # Clean up Celery process
            if celery_process and celery_process.poll() is None:
                self.stdout.write('  Terminating Celery worker...')
                celery_process.terminate()
                try:
                    celery_process.wait(timeout=5)
                    self.stdout.write(self.style.SUCCESS('  ✓ Celery worker stopped'))
                except subprocess.TimeoutExpired:
                    celery_process.kill()
                    self.stdout.write(self.style.WARNING('  ⚠️  Celery worker force-killed'))

    def _start_celery_worker(self):
        """Start Celery worker in a subprocess (non-blocking, continues if it fails)."""
        self.stdout.write(self.style.SUCCESS('✓ Starting Celery worker...'))
        
        env = os.environ.copy()
        
        try:
            # Start Celery worker
            process = subprocess.Popen(
                [
                    sys.executable,
                    '-m',
                    'celery',
                    '-A',
                    'smartcare_hms',
                    'worker',
                    '-l',
                    'info',
                    '--concurrency=2',  # Use 2 concurrent workers in development
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line-buffered
            )
            
            # Give Celery a moment to start and show startup messages
            time.sleep(2)
            
            if process.poll() is None:
                self.stdout.write(self.style.SUCCESS('  ✓ Celery worker started (PID: {})'.format(process.pid)))
                return process
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '  ⚠️  Celery worker failed to start. Redis may be unreachable.'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        '  Django will continue running. Notifications will NOT be sent until Celery starts.\n'
                    )
                )
                # Print any startup errors
                try:
                    output, _ = process.communicate(timeout=1)
                    if output:
                        self.stdout.write(self.style.WARNING('  Error: ' + output[:200]))
                except subprocess.TimeoutExpired:
                    pass
                return None

        except FileNotFoundError:
            self.stdout.write(
                self.style.WARNING(
                    '  ⚠️  Celery not installed. Run: pip install celery[redis]'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '  Django will continue running without background task support.\n'
                )
            )
            return None

    def _run_django_server(self, addrport):
        """Run Django development server."""
        from django.core.management import call_command
        
        try:
            call_command('runserver', addrport, use_reloader=True)
        except KeyboardInterrupt:
            raise


__all__ = ['Command']
