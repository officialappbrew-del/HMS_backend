from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from .models import LabTest, LabOrder, LabResult, NCDCReport, InstrumentMaintenance
from .serializers import (
    LabTestSerializer, LabOrderSerializer, LabResultSerializer,
    LabResultCreateSerializer, NCDCReportSerializer, NCDCReportSubmitSerializer,
    InstrumentMaintenanceSerializer
)
from core.permissions import IsDoctor, IsLabTechnician
from core.views import TenantScopedModelViewSet


class LabTestViewSet(TenantScopedModelViewSet):
    queryset = LabTest.objects.all()
    serializer_class = LabTestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)
        return queryset

    @action(detail=False, methods=['get'])
    def categories(self, request):
        categories = [
            {'value': 'hematology', 'label': 'Hematology'},
            {'value': 'biochemistry', 'label': 'Biochemistry'},
            {'value': 'microbiology', 'label': 'Microbiology'},
            {'value': 'urinalysis', 'label': 'Urinalysis'},
            {'value': 'hormonal', 'label': 'Hormonal'},
            {'value': 'immunology', 'label': 'Immunology'},
            {'value': 'molecular', 'label': 'Molecular'},
            {'value': 'other', 'label': 'Other'}
        ]
        return Response(categories)


class LabOrderViewSet(TenantScopedModelViewSet):
    queryset = LabOrder.objects.all()
    serializer_class = LabOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        patient_id = self.request.query_params.get('patient_id', None)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        
        priority = self.request.query_params.get('priority', None)
        if priority:
            queryset = queryset.filter(priority=priority)
        
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        ordered_by = getattr(user, 'tenant_user', None) if hasattr(user, 'tenant_user') else None
        if ordered_by:
            serializer.save(ordered_by=ordered_by)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def collect_sample(self, request, pk=None):
        order = self.get_object()
        order.status = 'collected'
        order.collected_by = request.user
        order.collected_date = timezone.now()
        if not order.sample_accession_number:
            order.sample_accession_number = f"ACC-{timezone.now().strftime('%Y%m%d')}-{str(order.id).zfill(6)}"
        order.save()
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def start_analysis(self, request, pk=None):
        order = self.get_object()
        order.status = 'in_progress'
        order.performed_by = request.user
        order.save()
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        order = self.get_object()
        order.status = 'completed'
        order.completed_date = timezone.now()
        order.save()
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        order.status = 'cancelled'
        order.save()
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        today = timezone.now().date()
        today_orders = LabOrder.objects.filter(tenant=tenant, ordered_date__date=today)
        
        stats = {
            'pending_samples': today_orders.filter(status='ordered').count(),
            'collected_samples': today_orders.filter(status='collected').count(),
            'in_progress': today_orders.filter(status='in_progress').count(),
            'completed_tests': today_orders.filter(status='completed').count(),
            'total_orders': today_orders.count(),
        }
        return Response(stats)

    @action(detail=False, methods=['get'])
    def critical_results(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        critical_orders = LabOrder.objects.filter(
            tenant=tenant,
            results__is_critical=True
        ).distinct().prefetch_related('results', 'patient', 'test', 'ordered_by')
        
        critical_data = []
        for order in critical_orders:
            latest_result = order.results.filter(is_critical=True).order_by('-created_at').first()
            if latest_result:
                critical_data.append({
                    'id': latest_result.id,
                    'order_id': order.id,
                    'patient_id': order.patient.id,
                    'patient_name': order.patient.get_full_name(),
                    'patient_identifier': order.patient.patient_identifier,
                    'test_name': order.test.name,
                    'value': latest_result.value,
                    'reference_range': latest_result.reference_range or order.test.reference_range,
                    'critical_since': latest_result.created_at.strftime('%Y-%m-%d %H:%M'),
                    'ordered_by': order.ordered_by.get_full_name() if order.ordered_by else 'N/A',
                    'status': 'awaiting'
                })
        
        return Response(critical_data)

    @action(detail=False, methods=['get'])
    def work_in_progress(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        orders = LabOrder.objects.filter(
            tenant=tenant,
            status__in=['collected', 'in_progress']
        ).prefetch_related(
            'patient', 'test', 'collected_by', 'performed_by'
        )[:100]
        
        work_data = []
        for order in orders:
            work_data.append({
                'id': order.id,
                'order_number': order.order_number,
                'accession': order.sample_accession_number,
                'patient': order.patient.get_full_name(),
                'patient_id': order.patient.id,
                'tests': [order.test.name],
                'test_name': order.test.name,
                'collection': order.collected_date.strftime('%I:%M %p') if order.collected_date else 'Pending',
                'collected_date': order.collected_date,
                'station': order.get_status_display(),
                'tat': self._calculate_tat(order),
                'priority': order.priority,
                'tech': order.performed_by.get_full_name() if order.performed_by else 
                        (order.collected_by.get_full_name() if order.collected_by else 'Pending'),
            })
        
        return Response(work_data)

    def _calculate_tat(self, order):
        if order.completed_date:
            delta = order.completed_date - order.ordered_date
            hours = delta.total_seconds() // 3600
            return f"{int(hours)}h"
        elif order.collected_date:
            delta = timezone.now() - order.ordered_date
            hours = delta.total_seconds() // 3600
            return f"{int(hours)}h"
        return 'Pending'


class LabResultViewSet(TenantScopedModelViewSet):
    queryset = LabResult.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return LabResultCreateSerializer
        return LabResultSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        
        order_id = self.request.query_params.get('order_id', None)
        if order_id:
            queryset = queryset.filter(order_id=order_id)
        
        critical_only = self.request.query_params.get('critical_only', None)
        if critical_only and critical_only.lower() == 'true':
            queryset = queryset.filter(is_critical=True)
        
        verified = self.request.query_params.get('verified', None)
        if verified is not None:
            queryset = queryset.filter(is_verified=(verified.lower() == 'true'))
        
        return queryset.prefetch_related('order', 'order__patient', 'order__test')

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        result = self.get_object()
        result.is_verified = True
        result.verified_by = request.user
        result.verified_date = timezone.now()
        result.save()
        serializer = self.get_serializer(result)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        result = self.get_object()
        result.result_notes = f"[ESCALATED] {timezone.now()}: {request.data.get('notes', 'Escalated to supervisor')}"
        result.save()
        serializer = self.get_serializer(result)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def critical(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        critical = LabResult.objects.filter(tenant=tenant, order__tenant=tenant, is_critical=True).prefetch_related(
            'order', 'order__patient', 'order__test'
        )
        serializer = self.get_serializer(critical, many=True)
        return Response(serializer.data)


class NCDCReportViewSet(TenantScopedModelViewSet):
    queryset = NCDCReport.objects.all()
    serializer_class = NCDCReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        report_type = self.request.query_params.get('report_type', None)
        if report_type:
            queryset = queryset.filter(report_type=report_type)
        
        return queryset

    @action(detail=False, methods=['post'])
    def submit(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = NCDCReportSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        report = NCDCReport.objects.create(
            tenant=tenant,
            report_type=data['report_type'],
            case_count=data['case_count'],
            lga=data['lga'],
            state=data['state'],
            notes=data.get('notes', ''),
            status='submitted',
            submitted_date=timezone.now()
        )
        
        output_serializer = self.get_serializer(report)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        report = self.get_object()
        report.status = 'acknowledged'
        report.save()
        serializer = self.get_serializer(report)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        pending = NCDCReport.objects.filter(tenant=tenant, status='draft')
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)


class InstrumentMaintenanceViewSet(TenantScopedModelViewSet):
    queryset = InstrumentMaintenance.objects.all()
    serializer_class = InstrumentMaintenanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        instrument = self.request.query_params.get('instrument', None)
        if instrument:
            queryset = queryset.filter(instrument_name__icontains=instrument)
        
        return queryset

    @action(detail=False, methods=['get'])
    def pending_maintenance(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        pending = InstrumentMaintenance.objects.filter(
            tenant=tenant,
            status__in=['pending', 'in_progress'],
            scheduled_date__lte=timezone.now().date() + timezone.timedelta(days=7)
        ).order_by('scheduled_date')
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        maintenance = self.get_object()
        maintenance.status = 'completed'
        maintenance.completed_date = timezone.now()
        maintenance.save()
        serializer = self.get_serializer(maintenance)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def request(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
