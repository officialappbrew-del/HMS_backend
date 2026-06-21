# SmartCare HMS - Healthcare Management System

A comprehensive, secure, and scalable Healthcare Management System built with Django and Django REST Framework, specifically designed for the Nigerian healthcare market.

## Features

### Security
- RSA Encryption for secure authentication
- Two-Factor Authentication (TOTP, SMS, Email)
- Field-level encryption for sensitive data
- Comprehensive audit logging
- NDPR and HIPAA compliance

### Multi-Tenant Architecture
- Domain-based multi-tenancy
- Isolated database schemas per tenant
- Global administration system
- Tenant management interface

### Clinical Features
- Electronic Medical Records (EMR)
- Clinical Decision Support System (CDS)
- Pharmacy management with inventory
- Laboratory management (LIS)
- Billing and NHIS integration
- Staff management and payroll

## Technology Stack

### Backend
- **Framework:** Django 4.2 + Django REST Framework
- **Database:** PostgreSQL with multi-tenant schemas
- **Cache:** Redis
- **Message Queue:** Celery
- **Search:** Elasticsearch
- **Containerization:** Docker + Docker Compose

### Security
- **Authentication:** JWT with RSA signatures
- **Encryption:** AES-256-GCM
- **2FA:** TOTP, SMS, Email
- **Monitoring:** Comprehensive audit logs

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Development Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd smartcare_hms





## Database Storage Locations:

### 1. **Global Users (System Admins)**
- **Storage**: `public` schema in database
- **Model**: `GlobalUser` (in `apps.users`)
- **Tables**: `users_globaluser` (public schema)

### 2. **Tenants (Healthcare Facilities)**
- **Storage**: `public` schema in database  
- **Model**: `Tenant` (in `apps.tenants`)
- **Tables**: `tenants_tenant` (public schema)

### 3. **Tenant Users (Hospital Staff/Patients)**
- **Storage**: Tenant-specific schema (e.g., `tenant_ABC123`)
- **Model**: `TenantUser` (in `apps.tenants`)
- **Tables**: `tenants_tenantuser` (tenant schema)

### 4. **Tenant Data (Patients, Clinical, etc.)**
- **Storage**: Tenant-specific schema
- **Models**: `Patient`, `ConsultationNote`, `Drug`, etc.
- **Tables**: In tenant schema only

## Endpoint References:

### Global Admin Endpoints (public schema):
```bash
# Create Tenant (Global Admin)
POST /api/v1/tenants/tenants/

# Manage Tenants (Global Admin)
GET    /api/v1/tenants/tenants/
PUT    /api/v1/tenants/tenants/{id}/
DELETE /api/v1/tenants/tenants/{id}/

# Suspend/Activate Tenant
POST /api/v1/tenants/tenants/{id}/suspend/
POST /api/v1/tenants/tenants/{id}/activate/

# Manage Global Users
POST /api/v1/auth/users/           # Create global admin
GET  /api/v1/auth/users/           # List global users
```

### Tenant Admin Endpoints (tenant schema):
```bash
# Create Tenant User (within a tenant)
POST /api/v1/tenants/users/        # Creates user in tenant schema

# Manage Tenant Users
GET    /api/v1/tenants/users/      # List tenant users
PUT    /api/v1/tenants/users/{id}/ # Update tenant user
DELETE /api/v1/tenants/users/{id}/ # Delete tenant user

# Patient Management (tenant data)
POST /api/v1/patients/patients/    # Create patient in tenant
GET  /api/v1/patients/patients/    # List patients in tenant
```

## Authentication Flow:

1. **Global Admin Login**: Uses `GlobalUser` from public schema
2. **Tenant User Login**: Uses `TenantUser` from tenant schema  
3. **Middleware**: Automatically routes to correct schema based on domain/subdomain

## Key Points:
- **Separation**: Global data (public) vs Tenant data (tenant schemas)
- **Isolation**: Each tenant has complete data isolation
- **Scalability**: Can scale tenants independently
- **Security**: Cross-tenant data leakage prevented by schema isolation