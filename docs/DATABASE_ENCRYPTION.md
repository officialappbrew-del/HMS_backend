# Database Encryption at Rest

## Overview

SmartCare HMS stores Protected Health Information (PHI), financial records, and operational data in PostgreSQL. Encryption at rest ensures that data remains unreadable even if the underlying storage is compromised.

## Requirements

- **NDPR Compliance**: Nigerian Data Protection Regulation requires appropriate security measures for personal data.
- **HIPAA-equivalent**: Clinical systems handling patient data must implement encryption safeguards.
- **Defense in depth**: Encryption protects against physical theft, backup leaks, and misconfigured storage.

## Implementation Options

### Option A: PostgreSQL File-System Encryption (Recommended for Self-Hosted)

Use LUKS (Linux) or BitLocker (Windows) to encrypt the volume where PostgreSQL data files reside.

```bash
# Example: LUKS setup on Ubuntu
sudo cryptsetup luksFormat /dev/xvdf
sudo cryptsetup open /dev/xvdf postgres_encrypted
sudo mkfs.ext4 /dev/mapper/postgres_encrypted
```

**Pros**: Transparent to the application, no code changes required.  
**Cons**: Does not protect against insider threats with OS access.

### Option B: AWS RDS Encryption (Recommended for Cloud)

Enable encryption at rest when provisioning the RDS instance:

```bash
aws rds modify-db-instance \
  --db-instance-identifier smartcare-hms-db \
  --storage-encrypted \
  --kms-key-id arn:aws:kms:...
```

**Pros**: Managed key rotation, IAM integration, audit logging.  
**Cons**: Requires AWS RDS.

### Option C: pgcrypto (Application-Level Column Encryption)

For highly sensitive fields (e.g., patient NIN, medical history), use PostgreSQL's `pgcrypto` extension:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt on insert
INSERT INTO patients_patient (nin, ...) 
VALUES (pgp_sym_encrypt('12345678901', 'encryption_key'), ...);

-- Decrypt on select
SELECT pgp_sym_decrypt(nin, 'encryption_key') FROM patients_patient;
```

**Pros**: Granular control, field-level encryption.  
**Cons**: Key management is application responsibility; performance overhead.

## Key Management

1. **Never store encryption keys in the same database as the encrypted data.**
2. Use a dedicated secrets manager:
   - AWS Secrets Manager
   - HashiCorp Vault
   - Azure Key Vault
3. Rotate keys annually or per compliance requirements.
4. Maintain a key escrow process for disaster recovery.

## Verification

After enabling encryption:

```bash
# Verify PostgreSQL data directory permissions
ls -la /var/lib/postgresql/data/

# Verify LUKS status
sudo cryptsetup status postgres_encrypted

# Verify RDS encryption
aws rds describe-db-instances --db-instance-identifier smartcare-hms-db \
  --query 'DBInstances[0].StorageEncrypted'
```

## Backup Encryption

All database backups must also be encrypted:

```bash
# Encrypt backup with GPG
pg_dump HMS_DB | gpg --symmetric --cipher-algo AES256 > encrypted_backup.dump.gpg
```

Store backup encryption keys separately from the backup files.

## Compliance Checklist

- [ ] Storage encryption enabled (LUKS / RDS / equivalent)
- [ ] Backup encryption configured
- [ ] Key management process documented
- [ ] Key rotation schedule established (annual minimum)
- [ ] Incident response plan includes key compromise procedures
- [ ] Annual penetration test includes storage-layer validation
