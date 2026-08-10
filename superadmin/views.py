"""Super Admin platform management views.

These endpoints operate on the *public* schema and provide platform-wide
oversight for global administrators (super_admin / system_admin / superuser).
All views require the ``IsSuperAdmin`` permission.
"""
import logging
from django.db import connection
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import SystemSetting, AuditLog
from core.permissions import IsSuperAdmin, HasTenantPermission, IsSeniorAdmin
from tenants.models import Tenant, TenantUser, SubscriptionPlan, SupportTicket
from users.models import GlobalUser

from .serializers import (
    TenantAdminListSerializer,
    TenantDetailSerializer,
    TenantUpdateSerializer,
    TenantCreateSerializer,
    PlatformUserListSerializer,
    AuditLogSerializer,
    SupportTicketSerializer,
    GlobalAdminSerializer,
)

logger = logging.getLogger(__name__)


class SuperAdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _ensure_public_schema():
    """Ensure we are querying the public schema (global data)."""
    try:
        connection.set_schema_to_public()
    except Exception:
        pass


def _count_users_per_tenant():
    """Return a dict mapping tenant_id -> user count, across all tenants."""
    counts = {}
    for tenant in Tenant.objects.filter(is_active=True):
        try:
            connection.set_schema(tenant.schema_name)
            counts[tenant.id] = TenantUser.objects.count()
        except Exception:
            counts[tenant.id] = 0
        finally:
            connection.set_schema_to_public()
    return counts


def _count_patients_per_tenant():
    """Return a dict mapping tenant_id -> patient count, across all tenants."""
    counts = {}
    from patients.models import Patient

    for tenant in Tenant.objects.filter(is_active=True):
        try:
            connection.set_schema(tenant.schema_name)
            counts[tenant.id] = Patient.objects.count()
        except Exception:
            counts[tenant.id] = 0
        finally:
            connection.set_schema_to_public()
    return counts


class TenantAnalyticsView(APIView):
    """Per-tenant growth & resource usage analytics for the super admin dashboard.

    For each tenant this reports:
      * Growth: total users / patients, patients added this month, added last
        month, and a month-over-month growth rate (%).
      * Resource usage: total document/media bytes on disk, document count,
        backup count + latest backup size, and storage utilization vs the
        tenant's subscription plan allowance (GB).
      * A 30-day trend of daily new-patient registrations for charting.

    Metrics are computed per-tenant by switching to each tenant's schema and
    reading data in isolation, then switching back to the public schema.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()

        import datetime
        today = timezone.now().date()
        days = int(request.query_params.get('days', 30))
        if days < 1:
            days = 30
        if days > 90:
            days = 90

        start_date = today - datetime.timedelta(days=days - 1)

        # One month / one-day boundaries for growth-rate calculation
        this_month_start = today.replace(day=1)
        if this_month_start.month == 1:
            last_month_start = this_month_start.replace(year=today.year - 1, month=12)
        else:
            last_month_start = this_month_start.replace(month=today.month - 1)

        tenants = list(Tenant.objects.filter(is_active=True).order_by('name'))
        rows = []

        for tenant in tenants:
            try:
                connection.set_schema(tenant.schema_name)

                from patients.models import Patient, PatientDocument
                from tenants.models import TenantBackup, TenantUser

                total_patients = Patient.objects.count()
                total_users = TenantUser.objects.count()

                # Patients added this month and last month for growth rate
                patients_this_month = Patient.objects.filter(
                    registration_date__date__gte=this_month_start
                ).count()
                patients_last_month = Patient.objects.filter(
                    registration_date__date__gte=last_month_start,
                    registration_date__date__lt=this_month_start,
                ).count()

                if patients_last_month > 0:
                    growth_rate = round((patients_this_month / patients_last_month) * 100 - 100, 2)
                elif patients_this_month > 0:
                    growth_rate = 100.0
                else:
                    growth_rate = 0.0

                # Document / media storage used (bytes)
                storage_query = PatientDocument.objects.filter(
                    file_size__isnull=False
                )
                storage_used_bytes = storage_query.aggregate(
                    total=Sum('file_size')
                )['total'] or 0
                document_count = PatientDocument.objects.count()

                # Backups
                backup_count = TenantBackup.objects.count()
                latest_backup = TenantBackup.objects.order_by('-start_time').first()

                # 30-day new-patient trend
                trend_data = []
                for offset in range(days):
                    day = start_date + datetime.timedelta(days=offset)
                    count = Patient.objects.filter(
                        registration_date__date=day
                    ).count()
                    trend_data.append({
                        'date': day.isoformat(),
                        'count': count,
                    })

                # Plan-based limits & utilization
                plan = tenant.subscription_plan
                max_users = getattr(plan, 'max_users', None) or 0
                max_patients = getattr(plan, 'max_patients', None) or 0
                max_storage_gb = getattr(plan, 'max_storage_gb', None) or 0

                storage_used_gb = storage_used_bytes / (1024 * 1024 * 1024)
                storage_util = round(
                    (storage_used_gb / max_storage_gb) * 100, 2
                ) if max_storage_gb else 0.0
                user_util = round(
                    (total_users / max_users) * 100, 2
                ) if max_users else 0.0
                patient_util = round(
                    (total_patients / max_patients) * 100, 2
                ) if max_patients else 0.0

                rows.append({
                    'tenant_id': str(tenant.public_id),
                    'tenant_name': tenant.name,
                    'tenant_code': tenant.code,
                    'subscription_status': tenant.subscription_status,
                    'plan_name': getattr(plan, 'name', None),
                    'growth': {
                        'total_users': total_users,
                        'total_patients': total_patients,
                        'patients_this_month': patients_this_month,
                        'patients_last_month': patients_last_month,
                        'growth_rate': growth_rate,
                    },
                    'usage': {
                        'storage_used_bytes': storage_used_bytes,
                        'storage_used_gb': round(storage_used_gb, 3),
                        'document_count': document_count,
                        'backup_count': backup_count,
                        'latest_backup_size_bytes': latest_backup.file_size if latest_backup else 0,
                    },
                    'limits': {
                        'max_users': max_users,
                        'max_patients': max_patients,
                        'max_storage_gb': max_storage_gb,
                    },
                    'utilization': {
                        'users': user_util,
                        'patients': patient_util,
                        'storage': storage_util,
                    },
                    'trend': trend_data,
                })
            except Exception as exc:
                # Keep the tenant in the list with zeroed metrics rather than
                # aborting the whole request on a single failing schema.
                logger.warning(f'Failed to gather analytics for tenant {tenant.name}: {exc}')
                rows.append({
                    'tenant_id': str(tenant.public_id),
                    'tenant_name': tenant.name,
                    'tenant_code': tenant.code,
                    'subscription_status': tenant.subscription_status,
                    'plan_name': None,
                    'growth': {
                        'total_users': 0, 'total_patients': 0,
                        'patients_this_month': 0, 'patients_last_month': 0,
                        'growth_rate': 0.0,
                    },
                    'usage': {
                        'storage_used_bytes': 0, 'storage_used_gb': 0,
                        'document_count': 0, 'backup_count': 0,
                        'latest_backup_size_bytes': 0,
                    },
                    'limits': {'max_users': 0, 'max_patients': 0, 'max_storage_gb': 0},
                    'utilization': {'users': 0, 'patients': 0, 'storage': 0},
                    'trend': [],
                })
            finally:
                connection.set_schema_to_public()

        # Platform-wide aggregates
        total_storage_bytes = sum(r['usage']['storage_used_bytes'] for r in rows)
        total_storage_gb = round(total_storage_bytes / (1024 * 1024 * 1024), 3)
        platform_limits = {
            'max_storage_gb': sum(
                t.subscription_plan.max_storage_gb for t in tenants
                if getattr(t.subscription_plan, 'max_storage_gb', None)
            ),
            'max_users': sum(
                t.subscription_plan.max_users for t in tenants
                if getattr(t.subscription_plan, 'max_users', None)
            ),
            'max_patients': sum(
                t.subscription_plan.max_patients for t in tenants
                if getattr(t.subscription_plan, 'max_patients', None)
            ),
        }

        # Fastest-growing tenants (by growth rate, descending)
        ranked_growth = sorted(
            rows, key=lambda r: r['growth']['growth_rate'], reverse=True
        )

        # Heaviest resource users (by storage used, descending)
        ranked_usage = sorted(
            rows, key=lambda r: r['usage']['storage_used_gb'], reverse=True
        )

        return Response({
            'days': days,
            'tenants': rows,
            'summary': {
                'total_tenants': len(rows),
                'total_patients': sum(r['growth']['total_patients'] for r in rows),
                'total_users': sum(r['growth']['total_users'] for r in rows),
                'total_storage_gb': total_storage_gb,
                'total_documents': sum(r['usage']['document_count'] for r in rows),
                'total_backups': sum(r['usage']['backup_count'] for r in rows),
            },
            'platform_limits': platform_limits,
            'top_growing': ranked_growth[:5],
            'top_usage': ranked_usage[:5],
        })


class PlatformAnalyticsView(APIView):
    """Platform overview statistics for the super admin dashboard."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()

        user_counts = _count_users_per_tenant()

        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.ACTIVE,
            is_active=True,
        ).count()
        trial_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.TRIAL,
        ).count()
        suspended_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.SUSPENDED,
        ).count()
        cancelled_tenants = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.CANCELLED,
        ).count()

        total_users = sum(user_counts.values())
        patient_counts = _count_patients_per_tenant()
        total_patients = sum(patient_counts.values())

        # Monthly revenue projection
        monthly_revenue = Tenant.objects.filter(
            subscription_status=Tenant.SubscriptionStatus.ACTIVE,
            is_active=True,
        ).aggregate(total=Sum('monthly_fee'))['total'] or 0

        # Tenants by facility type
        tenants_by_type = list(
            Tenant.objects.values('facility_type__name').annotate(
                count=Count('id')
            ).order_by('-count')
        )

        # Tenants by state
        tenants_by_state = list(
            Tenant.objects.values('state__name').annotate(
                count=Count('id')
            ).order_by('-count')[:8]
        )

        # Recent tenant activity (last 10 tenants by created_at)
        recent_tenants = Tenant.objects.order_by('-created_at')[:6]
        recent_tenants_data = TenantAdminListSerializer(
            recent_tenants, many=True,
            context={'user_counts': user_counts},
        ).data

        # Recent audit log activity
        recent_activity = AuditLog.objects.order_by('-timestamp')[:10]
        recent_activity_data = AuditLogSerializer(recent_activity, many=True).data

        return Response({
            'total_tenants': total_tenants,
            'active_tenants': active_tenants,
            'trial_tenants': trial_tenants,
            'suspended_tenants': suspended_tenants,
            'cancelled_tenants': cancelled_tenants,
            'total_users': total_users,
            'total_patients': total_patients,
            'active_subscriptions': active_tenants,
            'monthly_revenue': float(monthly_revenue),
            'tenants_by_facility_type': tenants_by_type,
            'tenants_by_state': tenants_by_state,
            'recent_tenants': recent_tenants_data,
            'recent_activity': recent_activity_data,
        })

class TenantAdminListView(APIView):
    """List all tenants (platform-wide)."""
    permission_classes = [IsSuperAdmin]

    def get_permissions(self):
        return [IsSuperAdmin(), HasTenantPermission('can_view_all_tenants')]

    def get(self, request):
        _ensure_public_schema()
        user_counts = _count_users_per_tenant()

        queryset = Tenant.objects.all()

        # Search
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(domain__icontains=search) |
                Q(email__icontains=search)
            )

        # Status filter
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(subscription_status=status_filter)

        # is_active filter
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        queryset = queryset.order_by('-created_at')

        paginator = SuperAdminPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = TenantAdminListSerializer(
            page, many=True, context={'user_counts': user_counts}
        )
        return paginator.get_paginated_response(serializer.data)


class TenantAdminDetailView(APIView):
    """Retrieve / update a single tenant's details."""
    permission_classes = [IsSuperAdmin]
    lookup_field = 'public_id'

    def get_permissions(self):
        return [IsSuperAdmin(), HasTenantPermission('can_suspend_tenants')]

    def get(self, request, public_id):
        _ensure_public_schema()
        tenant = Tenant.objects.filter(public_id=public_id).first()
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TenantDetailSerializer(tenant)
        return Response(serializer.data)

    def put(self, request, public_id):
        return self._update(request, public_id, partial=False)

    def patch(self, request, public_id):
        return self._update(request, public_id, partial=True)

    def _update(self, request, public_id, partial):
        _ensure_public_schema()
        tenant = Tenant.objects.filter(public_id=public_id).first()
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        old_values = {
            'name': tenant.name,
            'email': tenant.email,
            'phone': tenant.phone,
            'subscription_status': tenant.subscription_status,
            'is_active': tenant.is_active,
        }

        serializer = TenantUpdateSerializer(
            tenant, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        AuditLog.objects.create(
            user=request.user,
            action='update_tenant',
            resource_type='tenant',
            resource_id=str(tenant.public_id),
            title='Tenant updated',
            old_values=old_values,
            new_values={
                'name': tenant.name,
                'email': tenant.email,
                'phone': tenant.phone,
                'subscription_status': tenant.subscription_status,
                'is_active': tenant.is_active,
            },
        )

        return Response(TenantDetailSerializer(tenant).data)


class TenantAdminCreateView(APIView):
    """Create a new tenant from the super admin dashboard."""
    permission_classes = [IsSuperAdmin]

    def get_permissions(self):
        return [IsSuperAdmin(), HasTenantPermission('can_create_tenants')]

    def post(self, request):
        _ensure_public_schema()
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)

        # Create default settings + communication profile + departments
        from tenants.models import TenantSetting, CommunicationProfile, Department
        tenant = serializer.instance
        TenantSetting.objects.create(tenant=tenant)
        CommunicationProfile.objects.create(tenant=tenant)
        default_departments = [
            {'name': 'Administration', 'code': 'ADMIN', 'is_clinical': False},
            {'name': 'Outpatient Department', 'code': 'OPD', 'is_clinical': True},
            {'name': 'Inpatient Department', 'code': 'IPD', 'is_clinical': True},
            {'name': 'Emergency Department', 'code': 'ER', 'is_clinical': True},
            {'name': 'Pharmacy', 'code': 'PHARM', 'is_clinical': False},
            {'name': 'Laboratory', 'code': 'LAB', 'is_clinical': False},
            {'name': 'Billing', 'code': 'BILL', 'is_clinical': False},
        ]
        for dept in default_departments:
            Department.objects.create(tenant=tenant, **dept)

        AuditLog.objects.create(
            user=request.user,
            action='create_tenant',
            resource_type='tenant',
            resource_id=str(tenant.public_id),
            title='Tenant created',
            new_values={'name': tenant.name, 'domain': tenant.domain},
        )

        root_admin_data = serializer.validated_data.get('root_admin') or {}
        if root_admin_data:
            try:
                root_username = root_admin_data.get('username') or f"{root_admin_data['first_name'].lower()}.{root_admin_data['last_name'].lower()}".replace(' ', '_')
                unique_username = root_username
                counter = 1
                while TenantUser.objects.filter(tenant=tenant, username=unique_username).exists():
                    unique_username = f"{root_username}{counter}"
                    counter += 1

                if TenantUser.objects.filter(tenant=tenant, email=root_admin_data['email']).exists():
                    return Response(
                        {'error': 'A user with this email already exists for this tenant.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                admin_user = TenantUser.objects.create(
                    tenant=tenant,
                    username=unique_username,
                    email=root_admin_data['email'],
                    first_name=root_admin_data['first_name'],
                    last_name=root_admin_data['last_name'],
                    phone=root_admin_data.get('phone', ''),
                    role='admin',
                    employee_id=root_admin_data.get('employee_id') or root_admin_data.get('user_id') or None,
                    is_staff=True,
                    is_active=True,
                    is_root_admin=True,
                )
                admin_user.set_password(root_admin_data['password'])
                admin_user.save()

                AuditLog.objects.create(
                    user=request.user,
                    action='create_root_admin',
                    resource_type='tenant_user',
                    resource_id=str(admin_user.id),
                    new_values={
                        'email': admin_user.email,
                        'tenant': str(tenant.public_id),
                        'is_root_admin': True,
                    }
                )

                # Send welcome email in background
                try:
                    from django.conf import settings
                    from users.tasks import send_tenant_welcome_email_task
                    login_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
                    send_tenant_welcome_email_task.delay(
                        recipient_email=admin_user.email,
                        admin_name=admin_user.get_full_name() or admin_user.username,
                        tenant_name=tenant.name,
                        temporary_password=root_admin_data['password'],
                        login_url=login_url,
                        user_id=admin_user.id,
                    )
                except Exception as exc:
                    logger.warning(f'Failed to queue tenant welcome email: {exc}')

            except Exception as exc:
                logger.error(f'Failed to create root admin: {exc}')
                return Response(
                    {'error': f'Tenant created but root admin creation failed: {exc}'},
                    status=status.HTTP_201_CREATED,
                )

        return Response(
            TenantAdminListSerializer(tenant).data,
            status=status.HTTP_201_CREATED,
        )


class TenantToggleView(APIView):
    """Activate / deactivate a tenant."""
    permission_classes = [IsSuperAdmin]

    def get_permissions(self):
        return [IsSuperAdmin(), HasTenantPermission('can_suspend_tenants')]

    def post(self, request, public_id):
        _ensure_public_schema()
        tenant = Tenant.objects.filter(public_id=public_id).first()
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get('action', 'toggle')
        if action == 'activate':
            tenant.is_active = True
            if tenant.subscription_status == Tenant.SubscriptionStatus.SUSPENDED:
                tenant.subscription_status = Tenant.SubscriptionStatus.ACTIVE
            tenant.save()
            audit_action = 'activate_tenant'
        elif action == 'deactivate' or action == 'suspend':
            tenant.is_active = False
            tenant.subscription_status = Tenant.SubscriptionStatus.SUSPENDED
            tenant.save()
            audit_action = 'suspend_tenant'
        else:
            # Toggle based on current state
            tenant.is_active = not tenant.is_active
            tenant.save()
            audit_action = 'activate_tenant' if tenant.is_active else 'suspend_tenant'

        AuditLog.objects.create(
            user=request.user,
            action=audit_action,
            resource_type='tenant',
            resource_id=str(tenant.public_id),
            title='Tenant status changed',
            new_values={'is_active': tenant.is_active, 'subscription_status': tenant.subscription_status},
        )

        return Response({'detail': f'Tenant {"activated" if tenant.is_active else "deactivated"} successfully'})


class PlatformUserListView(APIView):
    """List all users across all tenants."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()
        results = []

        tenant_filter = request.query_params.get('tenant_id')
        tenants_qs = Tenant.objects.all()
        if tenant_filter:
            tenants_qs = tenants_qs.filter(public_id=tenant_filter)

        for tenant in tenants_qs:
            try:
                connection.set_schema(tenant.schema_name)
                qs = TenantUser.objects.all()
                search = request.query_params.get('search')
                if search:
                    qs = qs.filter(
                        Q(first_name__icontains=search) |
                        Q(last_name__icontains=search) |
                        Q(email__icontains=search) |
                        Q(employee_id__icontains=search) |
                        Q(username__icontains=search)
                    )
                role_filter = request.query_params.get('role')
                if role_filter:
                    qs = qs.filter(role=role_filter)
                is_active = request.query_params.get('is_active')
                if is_active is not None:
                    qs = qs.filter(is_active=is_active.lower() == 'true')

                for user in qs.order_by('-created_at')[:200]:
                    results.append({
                        'id': user.id,
                        'employee_id': user.employee_id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'full_name': user.get_full_name(),
                        'role': user.role,
                        'is_active': user.is_active,
                        'is_root_admin': user.is_root_admin,
                        'tenant_name': tenant.name,
                        'tenant_code': tenant.code,
                        'tenant_domain': tenant.domain,
                        'tenant_id': str(tenant.public_id),
                        'last_login': user.last_login,
                        'created_at': user.created_at,
                    })
            finally:
                connection.set_schema_to_public()

        # Sort by created_at desc
        results.sort(key=lambda u: u.get('created_at') or timezone.now(), reverse=True)

        # Client-side pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size

        return Response({
            'count': total,
            'next': page * page_size < total,
            'previous': page > 1,
            'results': results[start:end],
        })


class PlatformUserToggleView(APIView):
    """Activate / deactivate a user across tenants."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, tenant_id, user_id):
        _ensure_public_schema()
        tenant = Tenant.objects.filter(public_id=tenant_id).first()
        if not tenant:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            connection.set_schema(tenant.schema_name)
            user = TenantUser.objects.filter(id=user_id).first()
        finally:
            connection.set_schema_to_public()

        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        user.is_active = not user.is_active
        try:
            connection.set_schema(tenant.schema_name)
            user.save(update_fields=['is_active'])
        finally:
            connection.set_schema_to_public()

        AuditLog.objects.create(
            user=request.user,
            action='toggle_user',
            resource_type='tenant_user',
            resource_id=str(user.id),
            title='User status changed',
            new_values={'is_active': user.is_active, 'tenant': tenant.name},
        )

        return Response({'detail': f'User {"activated" if user.is_active else "deactivated"} successfully'})


class PlatformAuditLogsView(APIView):
    """Platform-wide audit trail with pagination."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()
        queryset = AuditLog.objects.all()

        action = request.query_params.get('action')
        if action:
            queryset = queryset.filter(action__icontains=action)

        resource_type = request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__date__lte=end_date)

        queryset = queryset.order_by('-timestamp', '-id')

        paginator = SuperAdminPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class SystemSettingsView(APIView):
    """Get / update platform-wide system settings."""
    permission_classes = [IsSuperAdmin]

    def _get_value(self, key, default=None):
        try:
            setting = SystemSetting.objects.get(key=key)
            return setting.value
        except SystemSetting.DoesNotExist:
            return default

    def _set_value(self, key, value, category='platform', data_type='string', description=''):
        setting, _ = SystemSetting.objects.get_or_create(
            key=key,
            defaults={'value': str(value), 'category': category, 'data_type': data_type, 'description': description},
        )
        if setting.value != str(value):
            setting.value = str(value)
            setting.save(update_fields=['value'])

    def get(self, request):
        _ensure_public_schema()
        settings_map = {}
        for s in SystemSetting.objects.all():
            settings_map[s.key] = self._coerce(s)

        # Merge defaults so the dashboard always has a stable shape
        defaults = {
            'maintenance_mode': self._get_value('maintenance_mode', 'false'),
            'allow_new_signups': self._get_value('allow_new_signups', 'true'),
            'default_subscription_plan_id': self._get_value('default_subscription_plan_id', ''),
            'max_users_per_tenant': self._get_value('max_users_per_tenant', '100'),
            'max_storage_per_tenant_gb': self._get_value('max_storage_per_tenant_gb', '10'),
            'platform_name': self._get_value('platform_name', 'SmartCare HMS'),
            'support_email': self._get_value('support_email', ''),
            'platform_email_provider': self._get_value('platform_email_provider', ''),
            'platform_sms_provider': self._get_value('platform_sms_provider', ''),
            'platform_email_cost_monthly': self._get_value('platform_email_cost_monthly', '0'),
            'platform_sms_cost_monthly': self._get_value('platform_sms_cost_monthly', '0'),
        }
        defaults.update(settings_map)

        plans = SubscriptionPlan.objects.all().order_by('display_order', 'price_monthly')
        return Response({
            'settings': defaults,
            'subscription_plans': [
                {
                    'id': p.id,
                    'name': p.name,
                    'code': p.code,
                    'price_monthly': p.price_monthly,
                    'price_quarterly': p.price_quarterly,
                    'price_yearly': p.price_yearly,
                    'max_users': p.max_users,
                    'max_patients': p.max_patients,
                    'max_storage_gb': p.max_storage_gb,
                    'email_limit_monthly': p.email_limit_monthly,
                    'sms_limit_monthly': p.sms_limit_monthly,
                    'email_service_cost_monthly': p.email_service_cost_monthly,
                    'sms_service_cost_monthly': p.sms_service_cost_monthly,
                    'service_providers': p.service_providers,
                }
                for p in plans
            ],
        })

    def put(self, request):
        _ensure_public_schema()
        data = request.data.get('settings') or request.data
        allowed_keys = {
            'maintenance_mode', 'allow_new_signups', 'default_subscription_plan_id',
            'max_users_per_tenant', 'max_storage_per_tenant_gb',
            'platform_name', 'support_email',
            'platform_email_provider', 'platform_sms_provider',
            'platform_email_cost_monthly', 'platform_sms_cost_monthly',
        }
        for key, value in data.items():
            if key not in allowed_keys:
                continue
            self._set_value(key, value, category='platform')

        AuditLog.objects.create(
            user=request.user,
            action='update_system_settings',
            resource_type='system_setting',
            resource_id='platform',
            title='Platform settings updated',
            new_values={k: data.get(k) for k in allowed_keys if k in data},
        )

        return Response({'detail': 'System settings updated successfully'})

    def _coerce(self, setting):
        """Coerce a SystemSetting value into its declared data_type."""
        value = setting.value
        if setting.data_type == 'boolean':
            return value.lower() in ('true', '1', 'yes')
        if setting.data_type == 'integer':
            try:
                return int(value)
            except (TypeError, ValueError):
                return value
        if setting.data_type == 'float':
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if setting.data_type == 'json':
            try:
                import json
                return json.loads(value)
            except (TypeError, ValueError):
                return value
        return value


class PlatformPatientListView(APIView):
    """List all patients across all tenants."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()
        from patients.models import Patient
        results = []

        tenant_filter = request.query_params.get('tenant_id')
        tenants_qs = Tenant.objects.all()
        if tenant_filter:
            tenants_qs = tenants_qs.filter(public_id=tenant_filter)

        for tenant in tenants_qs:
            try:
                connection.set_schema(tenant.schema_name)
                qs = Patient.objects.all()
                search = request.query_params.get('search')
                if search:
                    qs = qs.filter(
                        Q(hospital_number__icontains=search) |
                        Q(mrn__icontains=search) |
                        Q(login_id__icontains=search) |
                        Q(nhis_number__icontains=search) |
                        Q(nin__icontains=search) |
                        Q(first_name__icontains=search) |
                        Q(last_name__icontains=search) |
                        Q(middle_name__icontains=search) |
                        Q(phone__icontains=search) |
                        Q(email__icontains=search)
                    )
                status_filter = request.query_params.get('status')
                if status_filter:
                    qs = qs.filter(patient_status=status_filter)
                gender_filter = request.query_params.get('gender')
                if gender_filter:
                    qs = qs.filter(gender=gender_filter)
                is_active = request.query_params.get('is_active')
                if is_active is not None:
                    qs = qs.filter(is_active=is_active.lower() == 'true')

                for patient in qs.order_by('-registration_date')[:200]:
                    results.append({
                        'id': patient.id,
                        'hospital_number': patient.hospital_number,
                        'mrn': patient.mrn,
                        'login_id': patient.login_id,
                        'full_name': patient.get_full_name(),
                        'date_of_birth': patient.date_of_birth,
                        'age': patient.age,
                        'gender': patient.gender,
                        'patient_status': patient.patient_status,
                        'phone': patient.phone,
                        'phone2': patient.phone2,
                        'email': patient.email,
                        'nhis_number': patient.nhis_number,
                        'nin': patient.nin,
                        'address': patient.address,
                        'city': patient.city,
                        'state': patient.state,
                        'tenant_name': tenant.name,
                        'tenant_code': tenant.code,
                        'tenant_domain': tenant.domain,
                        'tenant_id': str(tenant.public_id),
                        'registration_date': patient.registration_date,
                        'last_visit': patient.last_visit,
                        'is_active': patient.is_active,
                    })
            finally:
                connection.set_schema_to_public()

        results.sort(key=lambda p: p.get('registration_date') or timezone.now(), reverse=True)

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size

        return Response({
            'count': total,
            'next': page * page_size < total,
            'previous': page > 1,
            'results': results[start:end],
        })


class SubscriptionAnalyticsView(APIView):
    """Platform-wide subscription analytics."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()
        from tenants.models import SubscriptionPlan

        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('display_order', 'price_monthly')
        plan_data = []
        total_monthly_revenue = 0
        total_quarterly_revenue = 0
        total_yearly_revenue = 0

        for plan in plans:
            tenant_count = Tenant.objects.filter(subscription_plan=plan).count()
            active_count = Tenant.objects.filter(
                subscription_plan=plan,
                subscription_status__in=['active', 'trial'],
                is_active=True,
            ).count()
            monthly_revenue = float(plan.price_monthly) * tenant_count
            quarterly_revenue = float(plan.price_quarterly) * tenant_count
            yearly_revenue = float(plan.price_yearly) * tenant_count
            total_monthly_revenue += monthly_revenue
            total_quarterly_revenue += quarterly_revenue
            total_yearly_revenue += yearly_revenue

            plan_data.append({
                'id': plan.id,
                'name': plan.name,
                'code': plan.code,
                'price_monthly': float(plan.price_monthly),
                'price_quarterly': float(plan.price_quarterly),
                'price_yearly': float(plan.price_yearly),
                'currency': plan.currency,
                'tenant_count': tenant_count,
                'active_count': active_count,
                'monthly_revenue': monthly_revenue,
                'quarterly_revenue': quarterly_revenue,
                'yearly_revenue': yearly_revenue,
                'max_users': plan.max_users,
                'max_patients': plan.max_patients,
                'max_storage_gb': plan.max_storage_gb,
                'email_limit_monthly': plan.email_limit_monthly,
                'sms_limit_monthly': plan.sms_limit_monthly,
                'email_service_cost_monthly': float(plan.email_service_cost_monthly),
                'sms_service_cost_monthly': float(plan.sms_service_cost_monthly),
                'service_providers': plan.service_providers,
                'is_default': plan.is_default,
                'is_trial_available': plan.is_trial_available,
                'trial_period_days': plan.trial_period_days,
            })

        return Response({
            'plans': plan_data,
            'total_monthly_revenue': total_monthly_revenue,
            'total_quarterly_revenue': total_quarterly_revenue,
            'total_yearly_revenue': total_yearly_revenue,
            'total_plans': len(plan_data),
            'total_tenants_on_plans': sum(p['tenant_count'] for p in plan_data),
        })


class SupportTicketListView(APIView):
    """List and create support tickets."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        _ensure_public_schema()
        tickets = SupportTicket.objects.all().order_by('-created_at')
        tenant_id = request.query_params.get('tenant_id')
        status_filter = request.query_params.get('status')
        priority_filter = request.query_params.get('priority')

        if tenant_id:
            tickets = tickets.filter(tenant_id=tenant_id)
        if status_filter:
            tickets = tickets.filter(status=status_filter)
        if priority_filter:
            tickets = tickets.filter(priority=priority_filter)

        serializer = SupportTicketSerializer(tickets, many=True)
        return Response(serializer.data)

    def post(self, request):
        _ensure_public_schema()
        serializer = SupportTicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SupportTicketDetailView(APIView):
    """Get, update, or delete a support ticket."""
    permission_classes = [IsSuperAdmin]

    def get(self, request, ticket_id):
        _ensure_public_schema()
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({'error': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketSerializer(ticket)
        return Response(serializer.data)

    def put(self, request, ticket_id):
        _ensure_public_schema()
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({'error': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = SupportTicketSerializer(ticket, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        if serializer.validated_data.get('status') == SupportTicket.Status.RESOLVED:
            ticket.resolved_at = timezone.now()
            ticket.save(update_fields=['resolved_at'])

        return Response(serializer.data)

    def delete(self, request, ticket_id):
        _ensure_public_schema()
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({'error': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)
        ticket.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GlobalAdminListView(APIView):
    """List and create global admins."""
    permission_classes = [IsSuperAdmin, IsSeniorAdmin]

    def get(self, request):
        _ensure_public_schema()
        requesting_user = request.user
        requesting_level = IsSeniorAdmin.ROLE_HIERARCHY.get(getattr(requesting_user, 'role', ''), 0)
        if getattr(requesting_user, 'is_superuser', False):
            requesting_level = max(IsSeniorAdmin.ROLE_HIERARCHY.values()) + 1

        admins = GlobalUser.objects.filter(
            role__in=[GlobalUser.GlobalRole.SUPER_ADMIN, GlobalUser.GlobalRole.SYSTEM_ADMIN]
        ).order_by('-date_joined')

        visible_admins = []
        for admin in admins:
            admin_level = IsSeniorAdmin.ROLE_HIERARCHY.get(admin.role, 0)
            if admin_level <= requesting_level:
                visible_admins.append(admin)

        serializer = GlobalAdminSerializer(visible_admins, many=True)
        return Response(serializer.data)

    def post(self, request):
        _ensure_public_schema()
        if not getattr(request.user, 'can_create_tenants', False) and not getattr(request.user, 'is_superuser', False):
            return Response(
                {'error': 'You do not have permission to create global admins.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = GlobalAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GlobalAdminDetailView(APIView):
    """Get, update, or delete a global admin."""
    permission_classes = [IsSuperAdmin, IsSeniorAdmin]

    def get(self, request, admin_id):
        _ensure_public_schema()
        admin = GlobalUser.objects.filter(id=admin_id).first()
        if not admin:
            return Response({'error': 'Admin not found'}, status=status.HTTP_404_NOT_FOUND)

        if not IsSeniorAdmin().can_manage(request.user, admin):
            return Response(
                {'error': 'You do not have permission to manage this admin.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = GlobalAdminSerializer(admin)
        return Response(serializer.data)

    def put(self, request, admin_id):
        _ensure_public_schema()
        admin = GlobalUser.objects.filter(id=admin_id).first()
        if not admin:
            return Response({'error': 'Admin not found'}, status=status.HTTP_404_NOT_FOUND)

        if not IsSeniorAdmin().can_manage(request.user, admin):
            return Response(
                {'error': 'You do not have permission to manage this admin.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = GlobalAdminSerializer(admin, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, admin_id):
        _ensure_public_schema()
        admin = GlobalUser.objects.filter(id=admin_id).first()
        if not admin:
            return Response({'error': 'Admin not found'}, status=status.HTTP_404_NOT_FOUND)
        if admin == request.user:
            return Response({'error': 'You cannot delete your own account'}, status=status.HTTP_400_BAD_REQUEST)

        if not IsSeniorAdmin().can_manage(request.user, admin):
            return Response(
                {'error': 'You do not have permission to delete this admin.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        admin.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
