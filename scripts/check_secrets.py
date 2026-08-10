#!/usr/bin/env python
"""
CI/CD secrets validation script for SmartCare HMS.

Checks that production-critical secrets are not using default/weak values.
Designed to run in CI pipelines (GitHub Actions, GitLab CI, etc.) and
as a pre-deployment sanity check.

Usage:
    python scripts/check_secrets.py [--env-file .env]
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Secrets that must be strong in production
REQUIRED_SECRETS = [
    'SECRET_KEY',
    'JWT_SIGNING_KEY',
    'ENCRYPTION_KEY',
    'DATABASE_URL',
    'REDIS_URL',
    'EMAIL_HOST_PASSWORD',
    'PAYSTACK_SECRET_KEY',
    'FLUTTERWAVE_SECRET_KEY',
    'SMS_API_KEY',
]

# Weak/default patterns to reject
WEAK_PATTERNS = [
    re.compile(r'^django-insecure-', re.IGNORECASE),
    re.compile(r'^changeme$', re.IGNORECASE),
    re.compile(r'^secret$', re.IGNORECASE),
    re.compile(r'^password$', re.IGNORECASE),
    re.compile(r'^your-32-char-key-for-encryption-change-this$', re.IGNORECASE),
    re.compile(r'^default-encryption-key-32-chars-long-here$', re.IGNORECASE),
    re.compile(r'^default$', re.IGNORECASE),
    re.compile(r'^test-signing-key', re.IGNORECASE),
    re.compile(r'^postgres:\/\/postgres:password@', re.IGNORECASE),
    re.compile(r'^postgres:\/\/postgres:pluralsight@', re.IGNORECASE),
    re.compile(r'^localhost:5432\/HMS_DB$', re.IGNORECASE),
]

# Minimum entropy requirements
MIN_SECRET_KEY_LENGTH = 50
MIN_ENCRYPTION_KEY_LENGTH = 32


def parse_env_file(path):
    """Parse a .env file and return a dict of key=value pairs."""
    env = {}
    if not Path(path).exists():
        return env
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            env[key] = value
    return env


def check_secret(key, value, env):
    """Check a single secret for strength."""
    issues = []
    if not value:
        issues.append(f'{key} is empty or missing')
        return issues

    for pattern in WEAK_PATTERNS:
        if pattern.search(value):
            issues.append(f'{key} matches weak/default pattern: {pattern.pattern}')
            break

    if key == 'SECRET_KEY' and len(value) < MIN_SECRET_KEY_LENGTH:
        issues.append(f'{key} is too short ({len(value)} chars, minimum {MIN_SECRET_KEY_LENGTH})')

    if key == 'ENCRYPTION_KEY' and len(value) < MIN_ENCRYPTION_KEY_LENGTH:
        issues.append(f'{key} is too short ({len(value)} chars, minimum {MIN_ENCRYPTION_KEY_LENGTH})')

    if key in ('DATABASE_URL', 'REDIS_URL'):
        if 'localhost' in value and 'HMS_DB' in value:
            issues.append(f'{key} points to localhost development database')

    return issues


def main():
    parser = argparse.ArgumentParser(description='Validate production secrets')
    parser.add_argument('--env-file', default='.env', help='Path to .env file')
    parser.add_argument('--strict', action='store_true', help='Fail on any warning')
    args = parser.parse_args()

    env = parse_env_file(args.env_file)
    if not env:
        print(f'Warning: {args.env_file} not found or empty. Checking environment variables only.')

    # Merge environment variables (env vars take precedence)
    for key in REQUIRED_SECRETS:
        if key not in env and key in os.environ:
            env[key] = os.environ[key]

    all_issues = []
    for key in REQUIRED_SECRETS:
        value = env.get(key, '')
        issues = check_secret(key, value, env)
        all_issues.extend(issues)

    if all_issues:
        print('SECRETS VALIDATION FAILED')
        print('-' * 40)
        for issue in all_issues:
            print(f'  - {issue}')
        print()
        print('Fix these issues before deploying to production.')
        sys.exit(1)

    print('SECRETS VALIDATION PASSED')
    print('All required secrets appear to be properly configured.')


if __name__ == '__main__':
    main()
