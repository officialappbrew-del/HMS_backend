from django.http import Http404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet
from .models import Ward, Bed, Admission
from .serializers import AdmissionSerializer


class AdmissionManagementViewSet(TenantScopedModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = AdmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _get_tenant(self, request):
        if hasattr(request.user, 'tenant_user') and request.user.tenant_user:
            return request.user.tenant_user.tenant
        return None

    def _resolve_admission(self, pk):
        queryset = self.get_queryset()
        if pk is None:
            raise Http404

        try:
            return queryset.get(id=int(pk))
        except (TypeError, ValueError, Admission.DoesNotExist):
            pass

        if isinstance(pk, str):
            normalized = pk.strip()
            if normalized.startswith('REQ') and normalized[3:]:
                admission = queryset.filter(request_id=normalized).first()
                if admission is not None:
                    return admission
            if normalized.startswith('ADM') and normalized[3:]:
                try:
                    return queryset.get(id=int(normalized[3:]))
                except (TypeError, ValueError, Admission.DoesNotExist):
                    pass

        return queryset.filter(request_id=str(pk)).first()

    def get_object(self):
        pk = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        obj = self._resolve_admission(pk)
        if obj is None:
            raise Http404
        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        tenant = self._get_tenant(request)
        wards = Ward.objects.filter(tenant=tenant) if tenant else Ward.objects.none()
        beds = Bed.objects.filter(tenant=tenant) if tenant else Bed.objects.none()

        summary = {
            'totalWards': wards.count(),
            'totalBeds': beds.count(),
            'availableBeds': beds.filter(status=Bed.Status.AVAILABLE).count(),
            'occupiedBeds': beds.filter(status=Bed.Status.OCCUPIED).count(),
            'reservedBeds': beds.filter(status=Bed.Status.RESERVED).count(),
        }
        return Response(summary)

    @action(detail=False, methods=['post'], url_path='create-request')
    def create_request(self, request):
        data = request.data.copy()
        tenant = self._get_tenant(request)
        if not tenant:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_403_FORBIDDEN)

        payload = {
            'patient_id': data.get('patientId') or data.get('patient_id') or 'PAT-UNKNOWN',
            'patient_name': data.get('patientName') or data.get('patient_name') or 'Unknown Patient',
            'source': data.get('source') or 'Direct Admission',
            'diagnosis': data.get('diagnosis') or 'Pending assessment',
            'preferred_ward_type': data.get('preferredWardType') or data.get('preferred_ward_type') or 'General Ward',
            'priority': data.get('priority') or 'Medium',
            'notes': data.get('notes') or '',
            'discharge_summary': data.get('dischargeSummary') or data.get('discharge_summary') or {},
            'transfer_history': data.get('transferHistory') or data.get('transfer_history') or [],
        }

        serializer = AdmissionSerializer(data=payload, context={'tenant': tenant})
        serializer.is_valid(raise_exception=True)
        admission = serializer.save()

        return Response({
            'message': 'Admission request created',
            'request': AdmissionSerializer(admission).data,
        })

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        admission = self.get_object()
        admission.status = Admission.AdmissionStatus.APPROVED
        admission.save(update_fields=['status', 'updated_at'])
        return Response({'message': 'Admission approved', 'request': AdmissionSerializer(admission).data})

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        admission = self.get_object()
        admission.status = Admission.AdmissionStatus.REJECTED
        admission.rejection_reason = request.data.get('reason', '')
        admission.save(update_fields=['status', 'rejection_reason', 'updated_at'])
        return Response({'message': 'Admission rejected', 'request': AdmissionSerializer(admission).data})

    @action(detail=True, methods=['post'], url_path='admit')
    def admit(self, request, pk=None):
        admission = self.get_object()
        admission.status = Admission.AdmissionStatus.ADMITTED
        admission.ward_id = request.data.get('wardId') or admission.ward_id
        admission.bed_id = request.data.get('bedId') or admission.bed_id
        admission.consultant_name = request.data.get('consultantName') or admission.consultant_name
        admission.consultant_specialty = request.data.get('consultantSpecialty') or admission.consultant_specialty
        admission.date_of_admission = request.data.get('dateOfAdmission') or timezone.now()
        admission.save(update_fields=['status', 'ward_id', 'bed_id', 'consultant_name', 'consultant_specialty', 'date_of_admission', 'updated_at'])
        return Response({'message': 'Admission recorded', 'request': AdmissionSerializer(admission).data})

    @action(detail=True, methods=['post'], url_path='transfer')
    def transfer(self, request, pk=None):
        admission = self.get_object()
        transfer_payload = {
            'toWardId': request.data.get('toWardId') or request.data.get('to_ward_id') or '',
            'toBedId': request.data.get('toBedId') or request.data.get('to_bed_id') or '',
            'reason': request.data.get('reason', ''),
            'transferredAt': timezone.now().isoformat(),
        }
        history = list(admission.transfer_history or [])
        history.append(transfer_payload)
        admission.transfer_history = history
        admission.ward_id = transfer_payload['toWardId'] or admission.ward_id
        admission.bed_id = transfer_payload['toBedId'] or admission.bed_id
        admission.status = Admission.AdmissionStatus.TRANSFERRED
        admission.save(update_fields=['transfer_history', 'ward_id', 'bed_id', 'status', 'updated_at'])
        return Response({'message': 'Transfer recorded', 'request': AdmissionSerializer(admission).data})

    @action(detail=True, methods=['post'], url_path='discharge')
    def discharge(self, request, pk=None):
        admission = self.get_object()
        summary_payload = request.data.get('summary') or request.data.get('dischargeSummary') or request.data or {}
        admission.status = Admission.AdmissionStatus.DISCHARGED
        admission.discharge_date = timezone.now()
        admission.discharge_summary = summary_payload
        if admission.date_of_admission:
            delta_days = max(1, int((admission.discharge_date - admission.date_of_admission).days or 1))
            admission.actual_stay = delta_days
        admission.save(update_fields=['status', 'discharge_date', 'discharge_summary', 'actual_stay', 'updated_at'])
        return Response({'message': 'Discharge processed', 'request': AdmissionSerializer(admission).data})
