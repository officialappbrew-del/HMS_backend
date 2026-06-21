# SmartCare HMS - Django Backend Implementation Plan

## Executive Summary

This document outlines the comprehensive backend implementation plan for SmartCare HMS, a domain-based multi-tenant SaaS platform designed specifically for the Nigerian healthcare market. The system integrates advanced security features including RSA encryption and two-factor authentication, while providing complete clinical workflow management.

## Architecture Overview

### Multi-Tenant SaaS Architecture

**Domain-Based Multi-Tenancy:**
- Each tenant (hospital/healthcare facility) operates on a separate domain
- Shared database with tenant isolation using Django's multi-tenant framework
- Tenant-specific configurations and customizations
- Scalable architecture supporting 1000+ concurrent tenants

**Technology Stack:**
- **Framework:** Django 4.2+ with Django REST Framework
- **Database:** PostgreSQL with tenant-aware schemas
- **Cache:** Redis for session management and caching
- **Message Queue:** Celery with Redis broker
- **Search:** Elasticsearch for clinical data indexing
- **File Storage:** AWS S3 with encryption
- **Security:** RSA encryption, OAuth2, JWT tokens

## Security Implementation

### RSA and Two-Factor Authentication

**RSA Key Management:**
```python
# models.py
class RSAKey(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    public_key = models.TextField()
    private_key_encrypted = models.TextField()  # Encrypted with master key
    key_fingerprint = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

class User2FA(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)
    backup_codes = models.JSONField(default=list)  # Encrypted
    last_used = models.DateTimeField(null=True)
    failed_attempts = models.IntegerField(default=0)
```

**Authentication Flow:**
1. User login with email/password or username/pasword
2. RSA signature verification for device authentication
3. 2FA challenge (TOTP/SMS/Push notification)
4. JWT token generation with tenant context
5. Session management with automatic logout

**Security Features:**
- End-to-end encryption for PHI data
- Field-level encryption for sensitive data
- Audit logging for all data access
- NDPR compliance with data residency in Nigeria
- HIPAA-compliant access controls

## Core Modules Implementation

### 1. Multi-Tenant Management

**Tenant Model:**
```python
class Tenant(models.Model):
    name = models.CharField(max_length=100)
    domain = models.CharField(max_length=100, unique=True)
    schema_name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    settings = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=50)
    max_users = models.IntegerField()
    max_patients = models.IntegerField()
    features = models.JSONField(default=dict)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
```

### 2. User Management & Authentication

**User Roles & Permissions:**
- System Administrator
- Hospital Administrator
- Doctor/Physician
- Nurse
- Pharmacist
- Lab Technician
- Receptionist
- Patient

**Advanced Authentication:**
```python
class CustomUser(AbstractUser):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=USER_ROLES)
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    rsa_public_key = models.TextField(null=True)
    two_fa_enabled = models.BooleanField(default=True)
    two_fa_method = models.CharField(max_length=20, choices=TWO_FA_METHODS)
    last_login_ip = models.GenericIPAddressField(null=True)
    login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True)
```

### 3. Electronic Medical Records (EMR)

**Patient Model:**
```python
class Patient(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    hospital_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10)
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    address = models.TextField()
    emergency_contact = models.JSONField()
    medical_alerts = models.TextField(blank=True)
    nhis_number = models.CharField(max_length=20, null=True)
    blood_group = models.CharField(max_length=5, null=True)
    genotype = models.CharField(max_length=5, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Clinical Documentation:**
- Encounter notes with Nigerian medical templates
- Chief complaint and history documentation
- Physical examination forms
- Progress notes and discharge summaries
- Nigerian disease-specific templates (Malaria, Typhoid, Sickle Cell, etc.)

### 4. Clinical Decision Support (CDS)

**Drug Interaction Engine:**
```python
class DrugInteraction(models.Model):
    drug_a = models.ForeignKey(Drug, related_name='interactions_a')
    drug_b = models.ForeignKey(Drug, related_name='interactions_b')
    interaction_type = models.CharField(max_length=20)
    severity = models.CharField(max_length=20)
    description = models.TextField()
    nigerian_context = models.TextField()  # Local considerations
    reference = models.CharField(max_length=200)
```

**Clinical Guidelines:**
- Nigerian treatment protocols
- NHIS standard treatment guidelines
- WHO essential medicines protocols
- Antibiotic stewardship rules
- Local antimicrobial resistance patterns

### 5. Pharmacy Management

**Medication Orders:**
```python
class MedicationOrder(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    prescriber = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.IntegerField()  # days
    route = models.CharField(max_length=50)
    instructions = models.TextField()
    status = models.CharField(max_length=20, choices=ORDER_STATUS)
    dispensed_at = models.DateTimeField(null=True)
    dispensed_by = models.ForeignKey(CustomUser, null=True, related_name='dispensed_orders')
```

**Inventory Management:**
- Drug inventory tracking
- Expiry date monitoring
- Low stock alerts
- NAFDAC compliance tracking
- Controlled substance management

### 6. Laboratory Management

**Lab Orders & Results:**
```python
class LabOrder(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    ordered_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    test_type = models.ForeignKey(LabTest, on_delete=models.CASCADE)
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS)
    status = models.CharField(max_length=20, choices=ORDER_STATUS)
    ordered_at = models.DateTimeField(auto_now_add=True)
    collected_at = models.DateTimeField(null=True)
    resulted_at = models.DateTimeField(null=True)

class LabResult(models.Model):
    order = models.OneToOneField(LabOrder, on_delete=models.CASCADE)
    technician = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    results = models.JSONField()  # Structured test results
    interpretation = models.TextField()
    critical_values = models.JSONField(default=list)
    approved_at = models.DateTimeField(null=True)
    approved_by = models.ForeignKey(CustomUser, null=True, related_name='approved_results')
```

### 7. NHIS Integration

**NHIS Claims Processing:**
```python
class NHISClaim(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    service_date = models.DateField()
    service_type = models.CharField(max_length=50)
    diagnosis_codes = models.JSONField()  # ICD-10 codes
    procedure_codes = models.JSONField()  # NHIS procedure codes
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    status = models.CharField(max_length=20, choices=CLAIM_STATUS)
    claim_number = models.CharField(max_length=50, unique=True)
    submitted_at = models.DateTimeField(null=True)
    processed_at = models.DateTimeField(null=True)
```

### 8. Billing & Financial Management

**Multi-Currency Billing:**
- Nigerian Naira primary currency
- Support for international patients
- NHIS tariff integration
- Private billing with insurance integration
- Payment gateway integration (Paystack, Flutterwave)

### 9. Staff Management & Payroll

**Employee Management:**
```python
class Employee(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    employee_number = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    position = models.CharField(max_length=100)
    salary_grade = models.ForeignKey(SalaryGrade, on_delete=models.CASCADE)
    employment_date = models.DateField()
    contract_type = models.CharField(max_length=20)
    qualifications = models.JSONField()
    licenses = models.JSONField()  # MDCN, Nursing Council, etc.
    performance_reviews = models.JSONField(default=list)
```

**Payroll Processing:**
- Automated payroll calculation
- Tax compliance (PAYE, Pension)
- Leave management
- Performance-based incentives

### 10. Equipment & Asset Management

**Medical Equipment Tracking:**
```python
class MedicalEquipment(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    equipment_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    manufacturer = models.CharField(max_length=100)
    model = models.CharField(max_length=50)
    serial_number = models.CharField(max_length=100)
    purchase_date = models.DateField()
    warranty_expiry = models.DateField()
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    status = models.CharField(max_length=20)
    maintenance_schedule = models.JSONField()
    last_maintenance = models.DateField(null=True)
    next_maintenance = models.DateField(null=True)
```

## Security Architecture Implementation

### Data Encryption Layers

**Field-Level Encryption:**
```python
class EncryptedField(models.TextField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value is None:
            return value
        return decrypt_data(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_data(value)

    def get_prep_value(self, value):
        if value is None:
            return value
        return encrypt_data(value)
```

**Database Encryption:**
- Transparent Data Encryption (TDE) at database level
- Separate encryption keys per tenant
- Hardware Security Module (HSM) integration

### Access Control & Audit

**Role-Based Access Control (RBAC):**
```python
class Permission(models.Model):
    name = models.CharField(max_length=100)
    codename = models.CharField(max_length=100)
    description = models.TextField()

class Role(models.Model):
    name = models.CharField(max_length=50)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    permissions = models.ManyToManyField(Permission)
    is_default = models.BooleanField(default=False)

class AuditLog(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    action = models.CharField(max_length=50)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50)
    old_values = models.JSONField(null=True)
    new_values = models.JSONField(null=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=100)
```

### Network Security

**API Security:**
- OAuth2/OpenID Connect implementation
- JWT tokens with tenant context
- Rate limiting and throttling
- API versioning and deprecation management

**Infrastructure Security:**
- AWS security groups and NACLs
- Web Application Firewall (WAF)
- DDoS protection
- Network segmentation

## Implementation Roadmap

### Phase 0: Foundation & Compliance (Month 1)
1. **Compliance Documentation Setup:**
   - NDPR compliance workbook creation
   - HIPAA security risk assessment template
   - NHIS accreditation documentation requirements
   - State Ministry of Health reporting templates

2. **Data Migration Strategy Development:**
   - Legacy system migration playbook (paper, Excel, other HMS)
   - Nigerian hospital data format conversion procedures
   - Patient record deduplication strategy
   - Medical terminology mapping (local to standardized)
   - Emergency rollback procedures

3. **RPO/RTO Definition & SLA Commitments:**
   - Patient records: RPO=0, RTO=1 hour
   - Audit logs: RPO=5 min, RTO=4 hours
   - System config: RPO=15 min, RTO=30 min
   - Financial data: RPO=15 min, RTO=2 hours

4. **Incident Response Plan Establishment:**
   - Breach notification procedures (24-hour NDPR requirement)
   - Forensic evidence preservation procedures
   - Communication templates for different incident types
   - Legal counsel engagement criteria

5. **Architecture Validation:**
   - Cross-tenant isolation validation scripts
   - Security architecture review with Nigerian experts
   - Performance baseline establishment

### Phase 1: Foundation (Months 2-4)
1. Multi-tenant architecture setup with tenant isolation validation
2. User authentication and RSA/2FA implementation
3. Basic patient management with clinical data integrity
4. Security framework implementation and key management
5. Database encryption setup and backup procedures
6. Global admin system implementation
7. Basic monitoring and observability framework

### Phase 2: Core Clinical Modules (Months 5-8)
1. EMR implementation with Nigerian clinical templates
2. Pharmacy management with NAFDAC integration
3. Laboratory system with LIS integration
4. Clinical decision support with Nigerian protocols
5. NHIS integration and claims processing
6. Nigerian ecosystem integrations (PCN, MLSC, MDCN)
7. Mobile money and SMS gateway integration
8. National Identity Number (NIN) validation
9. Load testing and performance optimization

### Phase 3: Advanced Features (Months 7-9)
1. Equipment management
2. Staff management and payroll
3. Billing and financial systems
4. Reporting and analytics
5. Mobile application backend

### Phase 4: Integration & Optimization (Months 13-15)
1. Advanced third-party integrations and API ecosystem
2. Performance optimization and scalability testing
3. Comprehensive testing (security, load, integration)
4. Deployment automation and CI/CD enhancement
5. Staff training and change management
6. Business continuity testing and validation
7. Compliance audit preparation and documentation

## Compliance & Regulatory Requirements

### NDPR Compliance
- Data residency in Nigeria (AWS Africa region)
- 7-year audit trail retention
- Patient consent management
- Data subject rights implementation
- Privacy impact assessments

### HIPAA Compliance
- PHI protection measures
- Security incident procedures
- Access control and audit controls
- Contingency planning

### NHIS Integration
- Standardized tariff structures
- Claims processing workflows
- Provider accreditation management
- Quality assurance reporting

## Technology Stack Details

### Backend Technologies
- **Django 4.2+:** Main web framework
- **Django REST Framework:** API development
- **PostgreSQL:** Primary database
- **Redis:** Caching and session management
- **Celery:** Background task processing
- **Elasticsearch:** Search functionality
- **AWS Services:** S3, CloudFront, Lambda, SES

### Security Technologies
- **Cryptography:** Python cryptography library
- **OAuth2:** Django OAuth Toolkit
- **JWT:** PyJWT with custom claims
- **2FA:** Django Two-Factor Authentication
- **Encryption:** AES-256-GCM for data at rest
- **SSL/TLS:** End-to-end encryption

### Monitoring & Logging
- **Application Monitoring:** Sentry for error tracking
- **Infrastructure Monitoring:** AWS CloudWatch
- **Security Monitoring:** Custom security event logging
- **Performance Monitoring:** New Relic APM

## Deployment Architecture

### Cloud Infrastructure
- **Primary Region:** AWS Africa (Cape Town)
- **Backup Region:** AWS Europe (Ireland)
- **CDN:** CloudFront for global content delivery
- **Load Balancing:** Application Load Balancer
- **Auto Scaling:** EC2 Auto Scaling Groups
- **Database:** RDS PostgreSQL with Multi-AZ

### Containerization
- **Docker:** Application containerization
- **Kubernetes:** Orchestration (Amazon EKS)
- **Helm:** Package management
- **CI/CD:** GitHub Actions with AWS CodePipeline

## Risk Assessment & Mitigation

### Security Risks
1. **Data Breach:** Mitigated by encryption, access controls, monitoring
2. **Unauthorized Access:** RBAC, MFA, session management
3. **Data Loss:** Multi-region backups, disaster recovery
4. **Compliance Violations:** Automated compliance monitoring, NDPR compliance workbook
5. **Cross-tenant Data Leakage:** Schema isolation, row-level security, validation scripts

### Operational Risks
1. **System Downtime:** High availability architecture, monitoring, manual fallback procedures
2. **Performance Issues:** Auto-scaling, caching, optimization, load testing
3. **Integration Failures:** Comprehensive testing, monitoring, vendor SLAs
4. **Data Migration:** Phased migration with rollback plans, legacy system migration playbook
5. **Scalability Bottlenecks:** Load testing plan, predictive scaling, hot tenant handling

### Business Risks
1. **Regulatory Changes:** Compliance monitoring, NHIS guideline update process
2. **Vendor Dependencies:** Third-party risk assessment, vendor management framework
3. **Technology Obsolescence:** Technology refresh roadmap, modernization planning
4. **Human Resource Risk:** Knowledge transfer documentation, cross-training programs
5. **Market Adoption:** Nigerian UX patterns, local language support, change management

### Clinical Risks
1. **Patient Safety:** Clinical data integrity checks, medication reconciliation
2. **Medical Errors:** Clinical decision support, prescription validation
3. **Regulatory Compliance:** NHIS accreditation, MDCN verification, clinical governance
4. **Data Quality:** Validation rules, audit trails, quality monitoring

### Financial Risks
1. **Revenue Recognition:** SaaS revenue rules for Nigeria, multi-currency handling
2. **Tax Compliance:** VAT, WHT calculation and remittance procedures
3. **Bad Debt:** Debt provisioning, write-off policies, payment reconciliation
4. **Cost Overruns:** Cost optimization, predictive scaling, budget monitoring

## Cost Optimization

### Infrastructure Costs
- Reserved instances for predictable workloads
- Auto-scaling for variable loads
- S3 intelligent tiering for storage
- CDN for static content delivery

### Development Costs
- Open-source components where possible
- Modular architecture for incremental development
- Automated testing and deployment
- Cloud-native services for cost efficiency

## Global User Account Implementation for Multi-Tenant Management

### Overview
For managing multiple tenants in a SaaS environment, we implement a global user system that operates outside tenant isolation. Global users can create, edit, delete, or suspend tenants across the entire platform.

### Architecture Design

**Global vs. Tenant Users:**
- **Global Users:** System administrators with access to all tenants
- **Tenant Users:** Users scoped to specific tenant data
- **Hybrid Access:** Global users can also access tenant-specific data when needed

**Database Schema:**
```python
# Public schema (shared across all tenants)
class GlobalUser(models.Model):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True)

    # Global user specific fields
    role = models.CharField(max_length=20, choices=GLOBAL_ROLES, default='admin')
    can_create_tenants = models.BooleanField(default=True)
    can_suspend_tenants = models.BooleanField(default=True)
    can_delete_tenants = models.BooleanField(default=False)  # Restricted permission

    # Security fields
    rsa_public_key = models.TextField(null=True)
    two_fa_enabled = models.BooleanField(default=True)
    two_fa_method = models.CharField(max_length=20, choices=TWO_FA_METHODS, default='totp')

    groups = models.ManyToManyField(Group, blank=True)
    user_permissions = models.ManyToManyField(Permission, blank=True)

class TenantUser(models.Model):
    # Existing tenant-scoped user model
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    username = models.CharField(max_length=150)
    email = models.EmailField()
    # ... other fields
    is_global_admin = models.BooleanField(default=False)  # Allows tenant user to have global access
```

### Authentication & Authorization

**Custom Authentication Backend:**
```python
class GlobalAuthenticationBackend:
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Check global users first
        try:
            user = GlobalUser.objects.get(username=username)
            if user.check_password(password):
                # Set global context
                request.global_user = user
                request.is_global_session = True
                return user
        except GlobalUser.DoesNotExist:
            pass

        # Check tenant users
        try:
            # Get tenant from domain or subdomain
            tenant = get_tenant_from_request(request)
            user = TenantUser.objects.get(
                username=username,
                tenant=tenant
            )
            if user.check_password(password):
                request.tenant = tenant
                request.is_global_session = False
                return user
        except TenantUser.DoesNotExist:
            pass

        return None

    def get_user(self, user_id):
        try:
            return GlobalUser.objects.get(pk=user_id)
        except GlobalUser.DoesNotExist:
            try:
                return TenantUser.objects.get(pk=user_id)
            except TenantUser.DoesNotExist:
                return None
```

**Middleware for Global Access:**
```python
class GlobalAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is global admin
        if hasattr(request, 'user') and request.user.is_authenticated:
            if isinstance(request.user, GlobalUser) or request.user.is_global_admin:
                # Allow access to all tenants
                request.global_access = True
                # Set current tenant context if accessing tenant-specific data
                if 'tenant_id' in request.GET or 'tenant' in request.POST:
                    tenant_id = request.GET.get('tenant_id') or request.POST.get('tenant')
                    try:
                        request.tenant = Tenant.objects.get(id=tenant_id)
                    except Tenant.DoesNotExist:
                        pass
            else:
                # Normal tenant isolation
                request.tenant = get_tenant_from_request(request)
                request.global_access = False

        response = self.get_response(request)
        return response
```

### Tenant Management API

**Global Admin Views:**
```python
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404

class TenantManagementViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAuthenticated, IsGlobalAdmin]

    def get_queryset(self):
        # Global admins can see all tenants
        if self.request.global_access:
            return Tenant.objects.all()
        return Tenant.objects.none()

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        tenant = get_object_or_404(Tenant, pk=pk)
        tenant.is_active = False
        tenant.save()

        # Log the action
        AuditLog.objects.create(
            user=request.user,
            action='suspend_tenant',
            resource_type='tenant',
            resource_id=str(tenant.id),
            new_values={'is_active': False}
        )

        return Response({'status': 'tenant suspended'})

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        tenant = get_object_or_404(Tenant, pk=pk)
        tenant.is_active = True
        tenant.save()

        AuditLog.objects.create(
            user=request.user,
            action='activate_tenant',
            resource_type='tenant',
            resource_id=str(tenant.id),
            new_values={'is_active': True}
        )

        return Response({'status': 'tenant activated'})

class IsGlobalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.global_access or
            (hasattr(request.user, 'is_global_admin') and request.user.is_global_admin)
        )
```

### Tenant Creation Process

**Global Admin Tenant Creation:**
```python
class TenantCreationView(APIView):
    permission_classes = [IsGlobalAdmin]

    def post(self, request):
        serializer = TenantCreationSerializer(data=request.data)
        if serializer.is_valid():
            # Create tenant
            tenant = Tenant.objects.create(
                name=serializer.validated_data['name'],
                domain=serializer.validated_data['domain'],
                schema_name=generate_schema_name(),
                subscription_plan=serializer.validated_data['plan']
            )

            # Create tenant schema
            create_tenant_schema(tenant.schema_name)

            # Create tenant admin user
            tenant_admin = TenantUser.objects.create(
                tenant=tenant,
                username=f"admin@{tenant.domain}",
                email=serializer.validated_data['admin_email'],
                role='admin',
                is_staff=True
            )
            tenant_admin.set_password(serializer.validated_data['admin_password'])
            tenant_admin.save()

            # Log creation
            AuditLog.objects.create(
                user=request.global_user,
                action='create_tenant',
                resource_type='tenant',
                resource_id=str(tenant.id),
                new_values=serializer.validated_data
            )

            return Response({
                'tenant_id': tenant.id,
                'domain': tenant.domain,
                'admin_credentials': {
                    'username': tenant_admin.username,
                    'email': tenant_admin.email
                }
            }, status=201)

        return Response(serializer.errors, status=400)
```

### Security Considerations

**Global User Security:**
- Global users must use RSA + 2FA by default
- Separate login endpoint for global admins
- Audit all global actions with tamper-proof logs
- IP whitelisting for global admin access
- Session timeout after 30 minutes of inactivity

**Access Control:**
- Global users cannot access patient PHI without explicit tenant context
- All tenant management actions are logged
- Global users can be restricted by IP, time, or location
- Emergency suspension capabilities for security incidents

### Implementation Steps

1. **Database Setup:**
   - Create public schema for global data
   - Implement tenant schema creation/migration scripts

2. **User Management:**
   - Create GlobalUser model
   - Update authentication backend
   - Implement global user registration

3. **Middleware & Permissions:**
   - Global access middleware
   - Custom permission classes
   - Update existing views for global access

4. **Admin Interface:**
   - Global admin dashboard
   - Tenant management interface
   - Audit log viewer

5. **Security Hardening:**
   - RSA key management for global users
   - Enhanced 2FA requirements
   - Network security for global endpoints

### Global Admin Dashboard Features

- **Tenant Overview:** List all tenants with status, subscription, user count
- **Tenant Creation:** Form to onboard new healthcare facilities
- **Tenant Management:** Edit settings, suspend/activate, upgrade plans
- **System Monitoring:** Global system health, security alerts
- **Audit Reports:** Comprehensive audit trails for compliance
- **Billing Management:** Subscription management across tenants

This implementation ensures global administrators can efficiently manage the multi-tenant ecosystem while maintaining strict security and audit controls.

## Conclusion

This implementation plan provides a comprehensive roadmap for building SmartCare HMS as a secure, scalable, and compliant healthcare management platform. The multi-tenant SaaS architecture with advanced security features positions the system to serve the Nigerian healthcare market effectively while meeting international standards.

The phased approach ensures manageable development cycles with clear milestones and deliverables. Regular security assessments, compliance audits, and performance monitoring will ensure the system remains robust and reliable.

Key success factors include:
- Strong security foundation with RSA and 2FA
- Nigerian healthcare context expertise
- Scalable multi-tenant architecture
- Comprehensive clinical workflow support
- Regulatory compliance (NDPR, HIPAA, NHIS)

The implementation will result in a world-class healthcare management system that enhances patient care, improves operational efficiency, and ensures data security and compliance.



pg_textsearch

now lets tart the implementation  in this directory

