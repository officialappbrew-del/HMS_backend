from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from clinical.views import TenantScopedModelViewSet, IsDoctorOrNurse
from .models import DrugInteraction, AllergyCheck, DosingGuideline, ClinicalGuideline, RiskAssessment, PatientAlert
from .serializers import (
    DrugInteractionSerializer, AllergyCheckSerializer,
    DosingGuidelineSerializer, ClinicalGuidelineSerializer,
    RiskAssessmentSerializer, PatientAlertSerializer
)


class DrugInteractionViewSet(TenantScopedModelViewSet):
    queryset = DrugInteraction.objects.all()
    serializer_class = DrugInteractionSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        drug = self.request.query_params.get('drug')
        if drug:
            qs = qs.filter(drug1__iexact=drug) | qs.filter(drug2__iexact=drug)
        return qs

    @action(detail=False, methods=['post'], url_path='check')
    def check(self, request):
        """Check interactions between multiple drugs."""
        drugs = request.data.get('drugs', [])
        if not drugs:
            return Response({'detail': 'No drugs provided.'}, status=400)
        interactions = []
        for i, drug1 in enumerate(drugs):
            for drug2 in drugs[i + 1:]:
                qs = self.get_queryset().filter(
                    (models.Q(drug1__iexact=drug1) & models.Q(drug2__iexact=drug2)) |
                    (models.Q(drug1__iexact=drug2) & models.Q(drug2__iexact=drug1))
                )
                interactions.extend(DrugInteractionSerializer(qs, many=True).data)
        return Response(interactions)


class AllergyCheckViewSet(TenantScopedModelViewSet):
    queryset = AllergyCheck.objects.all()
    serializer_class = AllergyCheckSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs


class DosingGuidelineViewSet(TenantScopedModelViewSet):
    queryset = DosingGuideline.objects.all()
    serializer_class = DosingGuidelineSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        drug = self.request.query_params.get('drug')
        category = self.request.query_params.get('category')
        if drug:
            qs = qs.filter(drug_name__icontains=drug)
        if category:
            qs = qs.filter(drug_category=category)
        return qs


class ClinicalGuidelineViewSet(TenantScopedModelViewSet):
    queryset = ClinicalGuideline.objects.all()
    serializer_class = ClinicalGuidelineSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        search = self.request.query_params.get('search')
        if category:
            qs = qs.filter(category=category)
        if search:
            qs = qs.filter(
                models.Q(title__icontains=search) |
                models.Q(description__icontains=search) |
                models.Q(recommendations__icontains=search)
            )
        return qs


class RiskAssessmentViewSet(TenantScopedModelViewSet):
    queryset = RiskAssessment.objects.all()
    serializer_class = RiskAssessmentSerializer
    permission_classes = [IsDoctorOrNurse]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        user = self.request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            serializer.save(calculated_by=user.tenant_user)

    def get_queryset(self):
        qs = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        risk_type = self.request.query_params.get('risk_type')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        if risk_type:
            qs = qs.filter(risk_type=risk_type)
        return qs


class PatientAlertViewSet(TenantScopedModelViewSet):
    queryset = PatientAlert.objects.all()
    serializer_class = PatientAlertSerializer
    permission_classes = [IsDoctorOrNurse]

    def get_queryset(self):
        qs = super().get_queryset()
        patient_id = self.request.query_params.get('patient')
        alert_type = self.request.query_params.get('alert_type')
        acknowledged = self.request.query_params.get('acknowledged')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        if alert_type:
            qs = qs.filter(alert_type=alert_type)
        if acknowledged is not None:
            qs = qs.filter(acknowledged=acknowledged.lower() == 'true')
        return qs

    @action(detail=True, methods=['post'], url_path='acknowledge')
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        user = request.user
        if hasattr(user, 'tenant_user') and user.tenant_user:
            alert.acknowledged = True
            alert.acknowledged_by = user.tenant_user
            alert.acknowledged_at = timezone.now()
            alert.save(update_fields=['acknowledged', 'acknowledged_by', 'acknowledged_at'])
        return Response({'status': 'acknowledged'})

    @action(detail=True, methods=['post'], url_path='dismiss')
    def dismiss(self, request, pk=None):
        alert = self.get_object()
        alert.dismissed = True
        alert.dismissed_at = timezone.now()
        alert.save(update_fields=['dismissed', 'dismissed_at'])
        return Response({'status': 'dismissed'})
