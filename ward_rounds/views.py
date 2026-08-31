from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets, status

from tenants.models import Tenant
from rest_framework.decorators import action
from rest_framework.response import Response

from core.views import TenantScopedModelViewSet
from core.permissions import IsDoctorOrNurse, IsClinicalStaff, IsTenantRootAdminOrGlobalAdmin
from patients.models import Patient
from .models import WardRound, HandoverNote, GrandRound, Ward, Bed
from .serializers import (
    WardRoundSerializer,
    HandoverNoteSerializer,
    GrandRoundSerializer,
    WardSerializer,
    BedSerializer
)


class WardRoundViewSet(TenantScopedModelViewSet):
    queryset = WardRound.objects.all()
    serializer_class = WardRoundSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        round_type = self.request.query_params.get('type')
        status_filter = self.request.query_params.get('status')
        if round_type:
            qs = qs.filter(round_type=round_type)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=['post'], url_path='start')
    def start_round(self, request, pk=None):
        ward_round = self.get_object()
        ward_round.status = 'In Progress'
        ward_round.start_time = timezone.now()
        ward_round.save(update_fields=['status', 'start_time'])
        return Response(WardRoundSerializer(ward_round).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete_round(self, request, pk=None):
        ward_round = self.get_object()
        notes = request.data.get('notes', '')
        actual_duration = request.data.get('actual_duration')
        ward_round.status = 'Completed'
        ward_round.completed_time = timezone.now()
        if notes:
            ward_round.notes = notes
        if actual_duration:
            ward_round.actual_duration = actual_duration
        ward_round.save(update_fields=['status', 'completed_time', 'notes', 'actual_duration'])
        return Response(WardRoundSerializer(ward_round).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_round(self, request, pk=None):
        ward_round = self.get_object()
        reason = request.data.get('reason', '')
        ward_round.status = 'Cancelled'
        ward_round.cancellation_reason = reason
        ward_round.save(update_fields=['status', 'cancellation_reason'])
        return Response(WardRoundSerializer(ward_round).data)

    @action(detail=True, methods=['post'], url_path='add-patient')
    def add_patient(self, request, pk=None):
        ward_round = self.get_object()
        patient_id = request.data.get('patientId')
        if not patient_id:
            return Response({'error': 'patientId is required'}, status=400)
        patients = ward_round.patients_list or []
        if patient_id not in patients:
            patients.append(patient_id)
            ward_round.patients_list = patients
            ward_round.save(update_fields=['patients_list'])
        return Response(WardRoundSerializer(ward_round).data)

    @action(detail=True, methods=['post'], url_path='remove-patient')
    def remove_patient(self, request, pk=None):
        ward_round = self.get_object()
        patient_id = request.data.get('patientId')
        if not patient_id:
            return Response({'error': 'patientId is required'}, status=400)
        patients = ward_round.patients_list or []
        ward_round.patients_list = [p for p in patients if p != patient_id]
        ward_round.save(update_fields=['patients_list'])
        return Response(WardRoundSerializer(ward_round).data)

    @action(detail=True, methods=['post'], url_path='add-team-member')
    def add_team_member(self, request, pk=None):
        ward_round = self.get_object()
        member = request.data
        if not member.get('name'):
            return Response({'error': 'member name is required'}, status=400)
        team = ward_round.team_members or []
        if not any(m.get('name') == member.get('name') for m in team):
            team.append(member)
            ward_round.team_members = team
            ward_round.save(update_fields=['team_members'])
        return Response(WardRoundSerializer(ward_round).data)

    @action(detail=True, methods=['post'], url_path='record-documentation')
    def record_documentation(self, request, pk=None):
        ward_round = self.get_object()
        patient_id = request.data.get('patientId') or request.data.get('patient_id')
        documentation = request.data.get('documentation')
        if not patient_id or not documentation:
            return Response({'error': 'patientId and documentation are required'}, status=400)
        docs = ward_round.round_documentation or {}
        docs[patient_id] = documentation
        ward_round.round_documentation = docs
        ward_round.save(update_fields=['round_documentation'])
        return Response(WardRoundSerializer(ward_round).data)


class HandoverNoteViewSet(TenantScopedModelViewSet):
    queryset = HandoverNote.objects.all()
    serializer_class = HandoverNoteSerializer
    permission_classes = [IsDoctorOrNurse]


class GrandRoundViewSet(TenantScopedModelViewSet):
    queryset = GrandRound.objects.all()
    serializer_class = GrandRoundSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=['post'], url_path='add-case-study')
    def add_case_study(self, request, pk=None):
        grand_round = self.get_object()
        case_study = request.data
        if not case_study.get('patientId') or not case_study.get('diagnosis'):
            return Response({'error': 'patientId and diagnosis are required'}, status=400)
        studies = grand_round.case_studies or []
        studies.append(case_study)
        grand_round.case_studies = studies
        grand_round.save(update_fields=['case_studies'])
        return Response(GrandRoundSerializer(grand_round).data)





class WardViewSet(TenantScopedModelViewSet):
    queryset = Ward.objects.all()
    serializer_class = WardSerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(ward_id__icontains=search) |
                Q(ward_name__icontains=search) |
                Q(supervisor__icontains=search)
            )
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            if 'ward_rounds_ward' in str(exc) and 'tenant_id' in str(exc) and 'ward_id' in str(exc):
                return Response({'detail': 'A ward with this ID already exists for this tenant.'}, status=status.HTTP_400_BAD_REQUEST)
            raise


class BedViewSet(TenantScopedModelViewSet):
    queryset = Bed.objects.all()
    serializer_class = BedSerializer
    permission_classes = [IsClinicalStaff]

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            constraint = str(exc)
            if 'ward_rounds_bed' in constraint and 'ward_id' in constraint and ('bed_number' in constraint or 'bed_id' in constraint):
                return Response({'detail': 'A bed with this number already exists in this ward.'}, status=status.HTTP_400_BAD_REQUEST)
            raise

    def get_queryset(self):
        queryset = super().get_queryset()
        ward_id = self.request.query_params.get('ward_id')
        status = self.request.query_params.get('status')
        search = self.request.query_params.get('search')

        if ward_id:
            queryset = queryset.filter(ward__ward_id=ward_id)
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(
                Q(bed_id__icontains=search) |
                Q(ward__ward_name__icontains=search) |
                Q(patient__hospital_number__icontains=search) |
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search)
            )
        return queryset

    @action(detail=True, methods=['post'], url_path='reserve')
    def reserve(self, request, pk=None):
        bed = self.get_object()
        patient_id = request.data.get('patientId') or request.data.get('patient_id')
        if not patient_id:
            return Response({'detail': 'patientId is required'}, status=status.HTTP_400_BAD_REQUEST)

        if bed.status != Bed.Status.AVAILABLE:
            return Response({'detail': 'Only available beds can be reserved.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(tenant=bed.tenant, hospital_number__iexact=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

        bed.status = Bed.Status.RESERVED
        bed.patient = patient
        bed.save(update_fields=['status', 'patient'])
        return Response(BedSerializer(bed).data)

    @action(detail=True, methods=['post'], url_path='occupy')
    def occupy(self, request, pk=None):
        bed = self.get_object()
        patient_id = request.data.get('patientId') or request.data.get('patient_id')
        if not patient_id:
            return Response({'detail': 'patientId is required'}, status=status.HTTP_400_BAD_REQUEST)

        if bed.status not in [Bed.Status.AVAILABLE, Bed.Status.RESERVED]:
            return Response({'detail': 'Bed cannot be occupied in its current status.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = Patient.objects.filter(tenant=bed.tenant, hospital_number__iexact=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)

        bed.status = Bed.Status.OCCUPIED
        bed.patient = patient
        bed.save(update_fields=['status', 'patient'])
        return Response(BedSerializer(bed).data)

    @action(detail=True, methods=['post'], url_path='release')
    def release(self, request, pk=None):
        bed = self.get_object()
        if bed.status not in [Bed.Status.OCCUPIED, Bed.Status.RESERVED]:
            return Response({'detail': 'Only reserved or occupied beds can be released.'}, status=status.HTTP_400_BAD_REQUEST)

        bed.status = Bed.Status.UNDER_CLEANING
        bed.patient = None
        bed.save(update_fields=['status', 'patient'])
        return Response(BedSerializer(bed).data)

    @action(detail=True, methods=['post'], url_path='mark-available')
    def mark_available(self, request, pk=None):
        bed = self.get_object()
        bed.status = Bed.Status.AVAILABLE
        bed.cleaning_status = Bed.CleaningStatus.CLEAN
        bed.save(update_fields=['status', 'cleaning_status'])
        return Response(BedSerializer(bed).data)
