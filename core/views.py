from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.utils import timezone
from django.db.models import Count, Q, F
from patients.models import Patient, PatientVisit
from clinical.models import Prescription, VitalSign, VitalSignAlert
from pharmacy.models import Drug
from billing.models import Invoice
from tenants.models import TenantUser, Department
from .models import (
    Country, State, LGA, FacilityType, Specialization,
    Language, SystemSetting, AuditLog
)
from .serializers import (
    CountrySerializer, StateSerializer, LGASerializer,
    FacilityTypeSerializer, SpecializationSerializer,
    LanguageSerializer, SystemSettingSerializer, AuditLogSerializer
)
from .permissions import IsSystemAdmin, IsAuditViewer


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    """Base viewset that limits querysets to the current tenant."""

    tenant_field = 'tenant'
    require_tenant = True

    def _get_request_tenant(self):
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            return user.tenant_user.tenant
        if hasattr(user, 'tenant') and user.tenant:
            return user.tenant
        return None

    def get_queryset(self):
        tenant = self._get_request_tenant()
        if tenant:
            return self.queryset.filter(**{self.tenant_field: tenant})
        return self.queryset.none()

    def get_object(self):
        return super().get_object()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        tenant = self._get_request_tenant()
        if tenant:
            context['tenant'] = tenant
        return context

    def perform_create(self, serializer):
        user = self.request.user
        tenant = self._get_request_tenant()
        if not tenant:
            raise PermissionDenied("Tenant context required.")
        serializer.save(**{self.tenant_field: tenant})

    def perform_update(self, serializer):
        tenant = self._get_request_tenant()
        if not tenant:
            raise PermissionDenied("Tenant context required.")
        obj_tenant_id = getattr(getattr(serializer.instance, self.tenant_field, None), 'pk', None)
        if obj_tenant_id is None or obj_tenant_id != tenant.pk:
            raise PermissionDenied("You do not have permission to update this record.")
        serializer.save()

    def perform_destroy(self, instance):
        tenant = self._get_request_tenant()
        if not tenant:
            raise PermissionDenied("Tenant context required.")
        obj_tenant_id = getattr(getattr(instance, self.tenant_field, None), 'pk', None)
        if obj_tenant_id is None or obj_tenant_id != tenant.pk:
            raise PermissionDenied("You do not have permission to delete this record.")
        super().perform_destroy(instance)

    def get_tenant(self):
        return self._get_request_tenant()


from rest_framework import exceptions


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.filter(is_active=True)
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class StateViewSet(viewsets.ModelViewSet):
    serializer_class = StateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        country_id = self.request.query_params.get('country_id')
        if country_id:
            return State.objects.filter(country_id=country_id)
        return State.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class LGAViewSet(viewsets.ModelViewSet):
    serializer_class = LGASerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        state_id = self.request.query_params.get('state_id')
        if state_id:
            return LGA.objects.filter(state_id=state_id)
        return LGA.objects.all()
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class FacilityTypeViewSet(viewsets.ModelViewSet):
    queryset = FacilityType.objects.all()
    serializer_class = FacilityTypeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class SpecializationViewSet(viewsets.ModelViewSet):
    queryset = Specialization.objects.all()
    serializer_class = SpecializationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class LanguageViewSet(viewsets.ModelViewSet):
    queryset = Language.objects.filter(is_active=True)
    serializer_class = LanguageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSystemAdmin()]
        return super().get_permissions()


class SystemSettingViewSet(viewsets.ModelViewSet):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
    permission_classes = [IsSystemAdmin]
    
    @action(detail=False, methods=['get'])
    def by_category(self, request):
        category = request.query_params.get('category', 'general')
        settings = SystemSetting.objects.filter(category=category)
        serializer = self.get_serializer(settings, many=True)
        return Response(serializer.data)


class DashboardInsightsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _build_payload(self, request):
        user = request.user
        tenant_user = getattr(user, 'tenant_user', None)
        if not tenant_user:
            return None, Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)

        tenant = tenant_user.tenant
        role = (tenant_user.role or '').lower()

        today = timezone.now().date()
        queryset = Patient.objects.filter(tenant=tenant)

        patient_count = queryset.count()
        waiting_visits = PatientVisit.objects.filter(tenant=tenant, visit_status__in=['waiting', 'triaged']).count()
        pending_prescriptions = Prescription.objects.filter(tenant=tenant, status='prescribed').count()
        low_stock_drugs = Drug.objects.filter(tenant=tenant, stock_quantity__lte=F('reorder_level')).count()
        overdue_invoices = Invoice.objects.filter(tenant=tenant, status='overdue').count()
        critical_alerts = VitalSignAlert.objects.filter(tenant=tenant, severity='critical', acknowledged=False).count()
        pending_vitals = VitalSign.objects.filter(tenant=tenant).count()

        alerts = []
        if role in {'doctor', 'nurse'}:
            urgent_patients = PatientVisit.objects.filter(tenant=tenant, visit_status__in=['waiting', 'in_consultation', 'awaiting_lab']).order_by('-checkin_time')[:5]
            for visit in urgent_patients:
                alerts.append({
                    'id': f'visit-{visit.id}',
                    'type': 'critical' if visit.triage_category == 'red' else 'warning',
                    'title': f'{visit.patient.get_full_name()} needs attention',
                    'message': f'Current status: {visit.get_visit_status_display()}',
                    'priority': 'high',
                    'href': '/patients',
                })

        if role == 'pharmacist':
            low_stock_items = Drug.objects.filter(tenant=tenant, stock_quantity__lte=F('reorder_level')).order_by('stock_quantity')[:5]
            for drug in low_stock_items:
                alerts.append({
                    'id': f'drug-{drug.id}',
                    'type': 'warning',
                    'title': f'{drug.name} needs restock',
                    'message': f'Only {drug.stock_quantity} left',
                    'priority': 'high',
                    'href': '/pharmacy',
                })

        if role == 'admin':
            recent_invoices = Invoice.objects.filter(tenant=tenant).order_by('-invoice_date')[:5]
            for invoice in recent_invoices:
                alerts.append({
                    'id': f'invoice-{invoice.id}',
                    'type': 'warning' if invoice.balance_due else 'info',
                    'title': f'{invoice.invoice_number} balance due',
                    'message': f'₦{invoice.balance_due}',
                    'priority': 'medium',
                    'href': '/billing',
                })

        tasks = []
        if role == 'doctor':
            tasks.extend([
                {'id': 'review', 'title': 'Review pending consultations', 'description': f'{waiting_visits} patients waiting for review', 'priority': 'high', 'href': '/consultation'},
                {'id': 'followup', 'title': 'Check recent lab results', 'description': 'Follow up on pending diagnostics', 'priority': 'medium', 'href': '/emr'},
            ])
        elif role == 'nurse':
            tasks.extend([
                {'id': 'vitals', 'title': 'Record or review vitals', 'description': f'{pending_vitals} recent vital signs available', 'priority': 'high', 'href': '/vital-signs'},
                {'id': 'rounds', 'title': 'Prepare ward rounds', 'description': 'Confirm patients needing bedside review', 'priority': 'medium', 'href': '/ward-rounds'},
            ])
        elif role == 'pharmacist':
            tasks.extend([
                {'id': 'dispense', 'title': 'Process pending prescriptions', 'description': f'{pending_prescriptions} prescriptions awaiting fulfilment', 'priority': 'high', 'href': '/pharmacy'},
                {'id': 'stock', 'title': 'Restock low inventory', 'description': f'{low_stock_drugs} items below reorder level', 'priority': 'medium', 'href': '/inventory'},
            ])
        elif role == 'admin':
            tasks.extend([
                {'id': 'ops', 'title': 'Review operations', 'description': f'{patient_count} patients and {overdue_invoices} overdue invoices', 'priority': 'high', 'href': '/dashboard'},
                {'id': 'staff', 'title': 'Monitor staffing and capacity', 'description': 'Check bed occupancy and staffing health', 'priority': 'medium', 'href': '/staff'},
            ])
        else:
            tasks.extend([
                {'id': 'general', 'title': 'Check daily priorities', 'description': 'Keep today’s workflow moving', 'priority': 'medium', 'href': '/dashboard'}
            ])

        quick_actions = []
        if role == 'doctor':
            quick_actions = [
                {'title': 'Consultation', 'href': '/consultation', 'icon': 'stethoscope'},
                {'title': 'EMR', 'href': '/emr', 'icon': 'file-text'},
                {'title': 'My Patients', 'href': '/patients', 'icon': 'users'},
            ]
        elif role == 'nurse':
            quick_actions = [
                {'title': 'Vital Signs', 'href': '/vital-signs', 'icon': 'activity'},
                {'title': 'Ward Rounds', 'href': '/ward-rounds', 'icon': 'bed'},
                {'title': 'Assigned Patients', 'href': '/patients', 'icon': 'users'},
            ]
        elif role == 'pharmacist':
            quick_actions = [
                {'title': 'Pharmacy', 'href': '/pharmacy', 'icon': 'pill'},
                {'title': 'Inventory', 'href': '/inventory', 'icon': 'box'},
                {'title': 'Prescriptions', 'href': '/pharmacy', 'icon': 'file-text'},
            ]
        elif role == 'admin':
            quick_actions = [
                {'title': 'Patients', 'href': '/patients', 'icon': 'users'},
                {'title': 'Billing', 'href': '/billing', 'icon': 'credit-card'},
                {'title': 'Staff', 'href': '/staff', 'icon': 'users'},
            ]

        summary = {
            'patients': patient_count,
            'waiting_visits': waiting_visits,
            'pending_prescriptions': pending_prescriptions,
            'low_stock_drugs': low_stock_drugs,
            'overdue_invoices': overdue_invoices,
            'critical_alerts': critical_alerts,
            'today': today.isoformat(),
        }

        return role, Response({
            'role': role,
            'summary': summary,
            'alerts': alerts[:6],
            'tasks': tasks[:4],
            'quick_actions': quick_actions,
        })

    def list(self, request):
        _, response = self._build_payload(request)
        return response

    @action(detail=False, methods=['get'])
    def dashboard_insights(self, request):
        return self.list(request)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuditViewer]

    def _get_request_tenant(self):
        """Resolve the tenant for the current request, if any."""
        user = getattr(self.request, 'user', None)
        if user is None:
            return None
        # Tenant users have `tenant` set directly by the auth layer.
        tenant = getattr(user, 'tenant', None)
        if tenant is not None:
            return tenant
        # Global users may be linked to a TenantUser via reverse OneToOne.
        try:
            tenant_user = user.tenant_user
            if tenant_user:
                return tenant_user.tenant
        except Exception:
            pass
        return None

    def get_queryset(self):
        queryset = AuditLog.objects.all()

        # Tenant scoping: a tenant-bound user only sees their tenant's logs.
        # Global/superusers without a tenant context see all logs.
        tenant = self._get_request_tenant()
        if tenant is not None:
            queryset = queryset.filter(tenant=tenant)

        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                timestamp__date__gte=start_date,
                timestamp__date__lte=end_date
            )
        
        # Filter by action
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action__icontains=action)
        
        # Filter by resource type
        resource_type = self.request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by patient/resource id for patient-specific audit drill-downs
        resource_id = self.request.query_params.get('resource_id')
        if resource_id:
            queryset = queryset.filter(resource_id=str(resource_id))

        # Always return the newest activity first for audit views and paginated APIs.
        return queryset.order_by('-timestamp', '-id')
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get audit log summary statistics."""
        total_logs = AuditLog.objects.count()
        today_logs = AuditLog.objects.filter(
            timestamp__date=timezone.now().date()
        ).count()
        
        # Count by action
        actions = AuditLog.objects.values('action').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        # Count by resource type
        resource_types = AuditLog.objects.values('resource_type').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        return Response({
            'total_logs': total_logs,
            'today_logs': today_logs,
            'top_actions': list(actions),
            'top_resource_types': list(resource_types),
        })