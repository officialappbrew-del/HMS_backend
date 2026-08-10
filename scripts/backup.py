#!/usr/bin/env python
"""
Database backup management for SmartCare HMS.

Provides commands to create, list, and restore PostgreSQL backups.
Designed to run as a cron job, Celery task, or manual management command.

Usage:
    python scripts/backup.py create [--compress] [--tenant-schemas]
    python scripts/backup.py list [--path backups/]
    python scripts/backup.py restore <backup_file> [--target-db <db_name>]
    python scripts/backup.py cleanup [--older-than 30] [--path backups/]
"""

import argparse
import datetime
import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Default backup directory
DEFAULT_BACKUP_DIR = BASE_DIR / 'backups'

# Retention policy: keep backups for 30 days by default
DEFAULT_RETENTION_DAYS = 30


def get_env(var_name, default=None):
    """Read environment variable from .env file if available."""
    env_file = BASE_DIR / '.env'
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith(f'{var_name}='):
                    return line.split('=', 1)[1].strip('"').strip("'")
    return os.environ.get(var_name, default)


def build_pg_dump_cmd(db_name, db_user, db_host, db_port, db_password, output_path, compress=False):
    """Build pg_dump command for a specific database."""
    cmd = [
        'pg_dump',
        f'--dbname=postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}',
        '--format=custom',
        '--no-owner',
        '--no-acl',
        f'--file={output_path}',
    ]
    return cmd


def create_backup(backup_dir, compress=True, tenant_schemas=False):
    """Create a database backup."""
    db_name = get_env('DB_NAME') or get_env('POSTGRES_DB') or 'HMS_DB'
    db_user = get_env('DB_USER') or get_env('POSTGRES_USER') or 'postgres'
    db_host = get_env('DB_HOST') or get_env('POSTGRES_HOST') or 'localhost'
    db_port = get_env('DB_PORT') or get_env('POSTGRES_PORT') or '5432'
    db_password = get_env('DB_PASSWORD') or get_env('POSTGRES_PASSWORD') or ''

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'hms_backup_{timestamp}.dump'
    output_path = backup_dir / filename

    print(f'Creating backup: {output_path}')
    cmd = build_pg_dump_cmd(db_name, db_user, db_host, db_port, db_password, str(output_path), compress=compress)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f'Backup created successfully: {output_path} ({output_path.stat().st_size} bytes)')
        return str(output_path)
    except subprocess.CalledProcessError as e:
        print(f'Backup failed: {e.stderr}', file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print('Error: pg_dump not found. Install PostgreSQL client tools.', file=sys.stderr)
        sys.exit(1)


def list_backups(backup_dir):
    """List available backups."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        print(f'Backup directory not found: {backup_dir}')
        return

    backups = sorted(backup_dir.glob('*.dump'), key=os.path.getmtime, reverse=True)
    if not backups:
        print('No backups found.')
        return

    print(f'Found {len(backups)} backup(s) in {backup_dir}:')
    for backup in backups:
        size = backup.stat().st_size
        mtime = datetime.datetime.fromtimestamp(backup.stat().st_mtime)
        print(f'  {backup.name}  ({size / 1024 / 1024:.1f} MB)  {mtime.isoformat()}')


def restore_backup(backup_file, target_db=None):
    """Restore a backup to a database."""
    backup_path = Path(backup_file)
    if not backup_path.exists():
        print(f'Backup file not found: {backup_file}', file=sys.stderr)
        sys.exit(1)

    db_name = target_db or get_env('DB_NAME') or get_env('POSTGRES_DB') or 'HMS_DB'
    db_user = get_env('DB_USER') or get_env('POSTGRES_USER') or 'postgres'
    db_host = get_env('DB_HOST') or get_env('POSTGRES_HOST') or 'localhost'
    db_port = get_env('DB_PORT') or get_env('POSTGRES_PORT') or '5432'
    db_password = get_env('DB_PASSWORD') or get_env('POSTGRES_PASSWORD') or ''

    print(f'Restoring {backup_path} to database {db_name}...')
    cmd = [
        'pg_restore',
        f'--dbname=postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}',
        '--clean',
        '--if-exists',
        '--no-owner',
        '--no-acl',
        str(backup_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print('Restore completed successfully.')
    except subprocess.CalledProcessError as e:
        print(f'Restore failed: {e.stderr}', file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print('Error: pg_restore not found. Install PostgreSQL client tools.', file=sys.stderr)
        sys.exit(1)


def cleanup_backups(backup_dir, older_than_days=DEFAULT_RETENTION_DAYS):
    """Remove backups older than the retention period."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return

    cutoff = datetime.datetime.now() - datetime.timedelta(days=older_than_days)
    removed = 0
    for backup in backup_dir.glob('*.dump'):
        mtime = datetime.datetime.fromtimestamp(backup.stat().st_mtime)
        if mtime < cutoff:
            backup.unlink()
            removed += 1
            print(f'Removed old backup: {backup.name}')

    print(f'Cleanup complete. Removed {removed} backup(s) older than {older_than_days} days.')


def main():
    parser = argparse.ArgumentParser(description='SmartCare HMS database backup manager')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # create
    create_parser = subparsers.add_parser('create', help='Create a new database backup')
    create_parser.add_argument('--path', default=str(DEFAULT_BACKUP_DIR), help='Backup directory')
    create_parser.add_argument('--no-compress', action='store_true', help='Disable compression')

    # list
    list_parser = subparsers.add_parser('list', help='List available backups')
    list_parser.add_argument('--path', default=str(DEFAULT_BACKUP_DIR), help='Backup directory')

    # restore
    restore_parser = subparsers.add_parser('restore', help='Restore a database backup')
    restore_parser.add_argument('backup_file', help='Path to backup file')
    restore_parser.add_argument('--target-db', help='Target database name (default: current DB)')

    # cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Remove old backups')
    cleanup_parser.add_argument('--older-than', type=int, default=DEFAULT_RETENTION_DAYS, help='Remove backups older than N days')
    cleanup_parser.add_argument('--path', default=str(DEFAULT_BACKUP_DIR), help='Backup directory')

    args = parser.parse_args()

    if args.command == 'create':
        create_backup(args.path, compress=not args.no_compress)
    elif args.command == 'list':
        list_backups(args.path)
    elif args.command == 'restore':
        restore_backup(args.backup_file, args.target_db)
    elif args.command == 'cleanup':
        cleanup_backups(args.path, older_than_days=args.older_than)


if __name__ == '__main__':
    main()
