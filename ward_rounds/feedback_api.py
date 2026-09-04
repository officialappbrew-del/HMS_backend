from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.views import TenantScopedModelViewSet
from .models import Ambulance, EmergencyBay, EmergencyCase, PatientFeedbackRecord, PatientSurvey, PatientComplaint, QualityImprovementPlan
from .serializers import (
    AmbulanceSerializer, EmergencyBaySerializer, EmergencyCaseSerializer, PatientFeedbackRecordSerializer, PatientSurveySerializer,
    PatientComplaintSerializer, QualityImprovementPlanSerializer,
)


class EmergencyBayViewSet(TenantScopedModelViewSet):
    queryset = EmergencyBay.objects.all()
    serializer_class = EmergencyBaySerializer
    permission_classes = [permissions.IsAuthenticated]


class AmbulanceViewSet(TenantScopedModelViewSet):
    queryset = Ambulance.objects.all()
    serializer_class = AmbulanceSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmergencyCaseViewSet(TenantScopedModelViewSet):
    queryset = EmergencyCase.objects.select_related('assigned_bay')
    serializer_class = EmergencyCaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def triage(self, request, pk=None):
        case = self.get_object()
        data = request.data.get('triageData') or request.data.get('triage_data') or {}
        case.triage_data = data
        case.triage_score = data.get('score')
        case.triage_color = data.get('color', '')
        case.triage_time = timezone.now()
        case.status = EmergencyCase.Status.TRIAGED
        case.save(update_fields=['triage_data', 'triage_score', 'triage_color', 'triage_time', 'status', 'updated_at'])
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=['post'], url_path='assign-bay')
    def assign_bay(self, request, pk=None):
        case = self.get_object()
        bay = EmergencyBay.objects.filter(tenant=case.tenant, bay_id=request.data.get('bayId')).first()
        if bay is None:
            return Response({'detail': 'Treatment bay not found.'}, status=400)
        case.assigned_bay = bay
        case.status = EmergencyCase.Status.IN_TREATMENT
        case.treatment_start_time = timezone.now()
        case.save(update_fields=['assigned_bay', 'status', 'treatment_start_time', 'updated_at'])
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        case = self.get_object()
        new_status = request.data.get('status')
        valid = {choice[0] for choice in EmergencyCase.Status.choices}
        if new_status not in valid:
            return Response({'detail': 'Invalid emergency case status.'}, status=400)
        case.status = new_status
        if new_status in {EmergencyCase.Status.DISCHARGED, EmergencyCase.Status.ADMITTED}:
            case.discharge_time = timezone.now()
            case.disposition = new_status
        case.save(update_fields=['status', 'discharge_time', 'disposition', 'updated_at'])
        return Response(self.get_serializer(case).data)


class TenantCrudViewSet(TenantScopedModelViewSet):
    permission_classes = [permissions.IsAuthenticated]


class PatientFeedbackViewSet(TenantCrudViewSet):
    queryset = PatientFeedbackRecord.objects.all()
    serializer_class = PatientFeedbackRecordSerializer


class PatientSurveyViewSet(TenantCrudViewSet):
    queryset = PatientSurvey.objects.all()
    serializer_class = PatientSurveySerializer

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        survey = self.get_object()
        survey.status = 'sent'
        survey.sent_at = timezone.now()
        survey.save(update_fields=['status', 'sent_at', 'updated_at'])
        return Response(self.get_serializer(survey).data)


class PatientComplaintViewSet(TenantCrudViewSet):
    queryset = PatientComplaint.objects.all()
    serializer_class = PatientComplaintSerializer

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        complaint = self.get_object()
        complaint.status = PatientComplaint.Status.RESOLVED
        complaint.resolution = request.data.get('resolution', complaint.resolution)
        complaint.resolved_at = timezone.now()
        complaint.save(update_fields=['status', 'resolution', 'resolved_at', 'updated_at'])
        return Response(self.get_serializer(complaint).data)

    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        complaint = self.get_object()
        complaint.status = PatientComplaint.Status.ESCALATED
        complaint.priority = 'critical'
        complaint.save(update_fields=['status', 'priority', 'updated_at'])
        return Response(self.get_serializer(complaint).data)


class QualityImprovementPlanViewSet(TenantCrudViewSet):
    queryset = QualityImprovementPlan.objects.all()
    serializer_class = QualityImprovementPlanSerializer