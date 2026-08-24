from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from core.views import TenantScopedModelViewSet
from core.permissions import IsClinicalStaff
from .models import MedicalRecord, ProgressNote, ClinicalDocument, ProblemList, Allergy
from .serializers import (
    MedicalRecordSerializer, ProgressNoteSerializer,
    ClinicalDocumentSerializer, ProblemListSerializer, AllergySerializer,
    PatientEMRTimelineSerializer, PatientEMRAlertSerializer
)
from patients.models import Patient, PatientVisit


class MedicalRecordViewSet(TenantScopedModelViewSet):
    queryset = MedicalRecord.objects.all()
    serializer_class = MedicalRecordSerializer
    permission_classes = [IsClinicalStaff]

    @action(detail=True, methods=['post'], url_path='sign')
    def sign(self, request, pk=None):
        record = self.get_object()
        record.is_active = False
        record.closed_at = timezone.now()
        record.closed_by = request.user.tenant_user
        record.save(update_fields=['is_active', 'closed_at', 'closed_by'])
        return Response({'status': 'signed'})

    @action(detail=False, methods=['get'], url_path='timeline')
    def timeline(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({'detail': 'patient_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(pk=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

        timeline = []
        for visit in PatientVisit.objects.filter(patient=patient).order_by('checkin_time'):
            timeline.append({
                'type': 'visit',
                'id': visit.id,
                'title': f"Visit {visit.visit_number}",
                'timestamp': visit.checkin_time.isoformat() if visit.checkin_time else timezone.now().isoformat(),
                'summary': visit.chief_complaint or visit.notes or 'Patient visit recorded',
                'meta': {'visit_status': visit.visit_status, 'visit_type': visit.visit_type},
            })

        for record in MedicalRecord.objects.filter(patient=patient).order_by('created_at'):
            timeline.append({
                'type': 'record',
                'id': record.id,
                'title': record.chief_complaint or 'Medical record created',
                'timestamp': record.created_at.isoformat(),
                'summary': record.history_of_present_illness or record.chief_complaint or 'Clinical record created',
                'meta': {'record_number': record.record_number, 'record_type': record.record_type},
            })

        for note in ProgressNote.objects.filter(medical_record__patient=patient).order_by('created_at'):
            timeline.append({
                'type': 'note',
                'id': note.id,
                'title': note.get_note_type_display(),
                'timestamp': note.created_at.isoformat(),
                'summary': note.assessment or note.plan or note.subjective or 'Clinical note recorded',
                'meta': {'author': getattr(note.author, 'get_full_name', lambda: '')(), 'note_type': note.note_type},
            })

        for problem in ProblemList.objects.filter(patient=patient).order_by('created_at'):
            timeline.append({
                'type': 'problem',
                'id': problem.id,
                'title': problem.problem,
                'timestamp': problem.created_at.isoformat(),
                'summary': problem.notes or f"Status: {problem.get_status_display()}",
                'meta': {'status': problem.status, 'icd10_code': problem.icd10_code},
            })

        for allergy in Allergy.objects.filter(patient=patient).order_by('created_at'):
            timeline.append({
                'type': 'allergy',
                'id': allergy.id,
                'title': allergy.allergen,
                'timestamp': allergy.created_at.isoformat(),
                'summary': f"{allergy.reaction} • {allergy.get_severity_display()}",
                'meta': {'severity': allergy.severity, 'allergy_type': allergy.allergy_type},
            })

        for document in ClinicalDocument.objects.filter(patient=patient).order_by('created_at'):
            timeline.append({
                'type': 'document',
                'id': document.id,
                'title': document.title,
                'timestamp': document.created_at.isoformat(),
                'summary': document.description or document.document_type,
                'meta': {'document_type': document.document_type},
            })

        timeline.sort(key=lambda item: item['timestamp'])
        serializer = PatientEMRTimelineSerializer({'patient_id': patient.id, 'timeline': timeline})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='alerts')
    def alerts(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({'detail': 'patient_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(pk=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

        allergies = [
            {
                'id': item.id,
                'allergen': item.allergen,
                'reaction': item.reaction,
                'severity': item.severity,
                'type': item.allergy_type,
            }
            for item in Allergy.objects.filter(patient=patient).order_by('-created_at')
        ]
        serializer = PatientEMRAlertSerializer({
            'patient_id': patient.id,
            'allergies': allergies,
            'dnr_order': patient.dnr_order,
            'dnr_order_reason': patient.dnr_order_reason,
            'dnr_order_date': patient.dnr_order_date,
        })
        return Response(serializer.data)


class ProgressNoteViewSet(TenantScopedModelViewSet):
    queryset = ProgressNote.objects.all()
    serializer_class = ProgressNoteSerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        record_id = self.request.query_params.get('medical_record')
        if record_id:
            qs = qs.filter(medical_record_id=record_id)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        tenant = None
        author = None
        if hasattr(user, 'tenant_user') and user.tenant_user:
            tenant = user.tenant_user.tenant
            author = user.tenant_user
        if not tenant:
            raise permissions.PermissionDenied("Tenant context required.")
        save_kwargs = {'tenant': tenant}
        if author:
            save_kwargs['author'] = author
        serializer.save(**save_kwargs)

    @action(detail=True, methods=['post'], url_path='sign')
    def sign(self, request, pk=None):
        note = self.get_object()
        note.is_signed = True
        note.signed_at = timezone.now()
        note.save(update_fields=['is_signed', 'signed_at'])
        return Response({'status': 'signed'})


class ClinicalDocumentViewSet(TenantScopedModelViewSet):
    queryset = ClinicalDocument.objects.all()
    serializer_class = ClinicalDocumentSerializer
    permission_classes = [IsClinicalStaff]


class ProblemListViewSet(TenantScopedModelViewSet):
    queryset = ProblemList.objects.all()
    serializer_class = ProblemListSerializer
    permission_classes = [IsClinicalStaff]

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        problem = self.get_object()
        problem.status = 'resolved'
        problem.resolved_at = timezone.now()
        problem.save(update_fields=['status', 'resolved_at'])
        return Response({'status': 'resolved'})


class AllergyViewSet(TenantScopedModelViewSet):
    queryset = Allergy.objects.all()
    serializer_class = AllergySerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        queryset = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset
