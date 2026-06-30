from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet, IsDoctorOrNurse
from .models import WardRound, HandoverNote, GrandRound
from .serializers import WardRoundSerializer, HandoverNoteSerializer, GrandRoundSerializer


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
