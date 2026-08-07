from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ConsultationNote, Prescription, VitalSign, EarlyWarningScore, VitalSignAlert
from .serializers import (
    ConsultationNoteSerializer, PrescriptionSerializer, VitalSignSerializer,
    EarlyWarningScoreSerializer, VitalSignAlertSerializer,
    PrescriptionInteractionCheckSerializer, MedicationHistorySerializer,
)
from core.views import TenantScopedModelViewSet
from patients.models import Patient
from core.permissions import IsDoctor, IsPharmacist, IsNurse, IsDoctorOrPharmacist, IsDoctorOrNurse, IsClinicalStaff


class ConsultationNoteViewSet(TenantScopedModelViewSet):
    queryset = ConsultationNote.objects.all()
    serializer_class = ConsultationNoteSerializer
    permission_classes = [IsDoctor]

    def get_queryset(self):
        queryset = super().get_queryset()
        visit_id = self.request.query_params.get('visit')
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(doctor=user.tenant_user)


class PrescriptionViewSet(TenantScopedModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [IsDoctorOrPharmacist]

    def get_queryset(self):
        queryset = super().get_queryset()
        visit_id = self.request.query_params.get('visit')
        if visit_id:
            queryset = queryset.filter(visit_id=visit_id)
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        prescription_status = self.request.query_params.get('status')
        if prescription_status:
            queryset = queryset.filter(status=prescription_status)
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(prescribed_by=user.tenant_user)

    @action(detail=False, methods=['get'], url_path='history')
    def medication_history(self, request):
        patient_id = request.query_params.get('patient')
        if not patient_id:
            return Response({'detail': 'patient is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(pk=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

        history_items = []
        for prescription in Prescription.objects.filter(patient=patient).order_by('-prescribed_date'):
            history_items.append({
                'id': prescription.id,
                'drug_name': prescription.drug_name,
                'dosage': prescription.dosage,
                'frequency': prescription.frequency,
                'duration': prescription.duration,
                'route': prescription.route,
                'status': prescription.status,
                'prescribed_date': prescription.prescribed_date.isoformat(),
            })

        warnings = []
        seen_drugs = {}
        for item in history_items:
            drug_name = (item.get('drug_name') or '').strip()
            if not drug_name:
                continue
            normalized = drug_name.lower()
            if normalized in seen_drugs:
                warnings.append({
                    'type': 'duplicate_drug',
                    'message': f"Medication '{drug_name}' appears multiple times in the patient history. Review for duplicate therapy or overdose risk.",
                    'drug_name': drug_name,
                })
            else:
                seen_drugs[normalized] = item

        if len(seen_drugs) > 1:
            warnings.append({
                'type': 'duplicate_class',
                'message': 'Multiple medications are present in the patient history; review for duplicate therapy.',
            })

        serializer = MedicationHistorySerializer({
            'patient_id': patient.id,
            'medications': history_items,
            'warnings': warnings,
        })
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='interaction-check')
    def interaction_check(self, request):
        serializer = PrescriptionInteractionCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        drug_names = serializer.validated_data.get('drug_names') or []
        prescription_ids = serializer.validated_data.get('prescription_ids') or []

        interactions = []
        if prescription_ids:
            prescriptions = Prescription.objects.filter(pk__in=prescription_ids)
            drug_names = [item.drug_name for item in prescriptions if item.drug_name]

        known_pairs = {
            ('warfarin', 'aspirin'): 'High risk of bleeding.',
            ('warfarin', 'ibuprofen'): 'High risk of bleeding.',
            ('amiodarone', 'simvastatin'): 'Risk of myopathy.',
            ('lithium', 'ibuprofen'): 'Risk of lithium toxicity.',
            ('digoxin', 'clarithromycin'): 'Potential digoxin toxicity.',
            ('metformin', 'cimetidine'): 'Risk of hypoglycemia.',
        }

        normalized = [name.lower() for name in drug_names if name]
        for index, drug_a in enumerate(normalized):
            for drug_b in normalized[index + 1:]:
                pair = tuple(sorted((drug_a, drug_b)))
                if pair in known_pairs:
                    interactions.append({
                        'drugs': [drug_a, drug_b],
                        'severity': 'high',
                        'message': known_pairs[pair],
                    })

        return Response({'interactions': interactions})


class VitalSignViewSet(TenantScopedModelViewSet):
    queryset = VitalSign.objects.all()
    serializer_class = VitalSignSerializer
    permission_classes = [IsClinicalStaff]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(recorded_by=user.tenant_user)


class EarlyWarningScoreViewSet(TenantScopedModelViewSet):
    queryset = EarlyWarningScore.objects.all()
    serializer_class = EarlyWarningScoreSerializer
    permission_classes = [IsDoctorOrNurse]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(calculated_by=user.tenant_user)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """Calculate EWS from submitted vital signs without persisting."""
        data = request.data
        required = ['respiration_rate', 'oxygen_saturation', 'temperature', 'systolic_bp', 'heart_rate', 'consciousness']
        missing = [f for f in required if f not in data]
        if missing:
            return Response({'detail': f'Missing fields: {missing}'}, status=status.HTTP_400_BAD_REQUEST)
        
        result = EarlyWarningScore.calculate_newts2_score(
            respiration_rate=int(data['respiration_rate']),
            oxygen_saturation=float(data['oxygen_saturation']),
            temperature=float(data['temperature']),
            systolic_bp=int(data['systolic_bp']),
            heart_rate=int(data['heart_rate']),
            consciousness=data['consciousness']
        )
        return Response(result)


class VitalSignAlertViewSet(TenantScopedModelViewSet):
    queryset = VitalSignAlert.objects.all()
    serializer_class = VitalSignAlertSerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        queryset = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        acknowledged = self.request.query_params.get('acknowledged')
        if acknowledged is not None:
            queryset = queryset.filter(acknowledged=acknowledged.lower() == 'true')
        resolved = self.request.query_params.get('resolved')
        if resolved is not None:
            queryset = queryset.filter(resolved=resolved.lower() == 'true')
        return queryset

    @action(detail=True, methods=['post'], url_path='acknowledge')
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.acknowledged = True
            alert.acknowledged_by = user.tenant_user
            alert.acknowledged_at = timezone.now()
            alert.save()
        return Response({'status': 'acknowledged'})

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.resolved = True
            alert.resolved_by = user.tenant_user
            alert.resolved_at = timezone.now()
            alert.resolution_notes = request.data.get('resolution_notes', '')
            alert.save()
        return Response({'status': 'resolved'})

    @action(detail=False, methods=['get'], url_path='active')
    def active(self, request):
        queryset = self.get_queryset().filter(resolved=False)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
