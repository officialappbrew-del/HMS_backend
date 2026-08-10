# Database Backup and Restore Runbook

## Overview

SmartCare HMS stores all clinical, billing, and operational data in a single PostgreSQL database. This runbook documents the backup and restore procedures to ensure business continuity and compliance with data retention requirements.

## Backup Strategy

- **Frequency**: Daily automated backups at 02:00 AM server time
- **Retention**: 30 days of daily backups
- **Format**: PostgreSQL custom format (`pg_dump --format=custom`)
- **Location**: `/backups/` directory (mounted volume in production)
- **Encryption**: Backups should be encrypted at rest (S3 server-side encryption or filesystem encryption)

## Creating Backups

### Manual Backup

```bash
python scripts/backup.py create
```

### Backup with Custom Path

```bash
python scripts/backup.py create --path /mnt/backups/hms/
```

### List Existing Backups

```bash
python scripts/backup.py list
```

### Automated Backup (Cron)

Add to crontab (`crontab -e`):

```
0 2 * * * cd /app && python scripts/backup.py create --path /backups/
```

### Automated Cleanup

```bash
python scripts/backup.py cleanup --older-than 30
```

## Restoring Backups

### Prerequisites

- PostgreSQL client tools (`pg_dump`, `pg_restore`) installed
- Access to the target database server
- Sufficient disk space for the backup file
- Maintenance window approved (restore will cause downtime)

### Restore Procedure

1. **Notify stakeholders** and schedule maintenance window
2. **Verify backup integrity**:
   ```bash
   python scripts/backup.py list
   ls -lh /backups/
   ```
3. **Stop the application** to prevent writes during restore:
   ```bash
   # Render
   render scale --name smartcare-hms web=0

   # Docker Compose
   docker-compose stop web celery celery-beat
   ```
4. **Create a safety backup** of the current database before restoring:
   ```bash
   python scripts/backup.py create --path /backups/pre-restore/
   ```
5. **Drop and recreate the target database** (optional, use `--clean` with pg_restore instead):
   ```bash
   psql -U postgres -c "DROP DATABASE IF EXISTS HMS_DB;"
   psql -U postgres -c "CREATE DATABASE HMS_DB WITH OWNER postgres;"
   ```
6. **Restore the backup**:
   ```bash
   python scripts/backup.py restore /backups/hms_backup_20260807_020000.dump --target-db HMS_DB
   ```
7. **Run migrations** (if needed):
   ```bash
   python manage.py migrate --run-syncdb
   ```
8. **Restart the application**:
   ```bash
   # Render
   render scale --name smartcare-hms web=1

   # Docker Compose
   docker-compose up -d web celery celery-beat
   ```
9. **Verify the restore**:
   - Check application logs for errors
   - Verify patient records, appointments, and billing data
   - Run `/health/` endpoint to confirm DB connectivity
   - Test login with a known user account

## Disaster Recovery

### RTO (Recovery Time Objective): 4 hours
### RPO (Recovery Point Objective): 24 hours (daily backups)

### Incident Response

1. Assess data loss scope (which tenants/patients are affected)
2. Identify the last known good backup
3. Follow the restore procedure above
4. Notify affected tenants and regulatory bodies if PHI was compromised
5. Document the incident and update this runbook

### Off-Site Backup

For additional resilience:
- Copy daily backups to S3 or equivalent object storage
- Enable cross-region replication for production databases
- Test restore procedures quarterly

## Backup Verification

Run this script to verify backup integrity:

```bash
python scripts/backup.py list
# Check file sizes and timestamps
# Test restore to a staging database monthly
```

## Retention Compliance

- Daily backups retained for 30 days
- Monthly backups retained for 1 year (archive to S3)
- Yearly backups retained for 7 years (compliance requirement)
- Automatically purge backups exceeding retention via `cleanup` command
