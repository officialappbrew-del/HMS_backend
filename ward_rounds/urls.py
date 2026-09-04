from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WardRoundViewSet, HandoverNoteViewSet, GrandRoundViewSet, WardViewSet, BedViewSet
from .admission_api import AdmissionManagementViewSet
from .emergency_api import EmergencyCallViewSet, AmbulanceMissionViewSet, ReferralRequestViewSet
from .feedback_api import (
    AmbulanceViewSet, EmergencyBayViewSet, EmergencyCaseViewSet, PatientFeedbackViewSet, PatientSurveyViewSet,
    PatientComplaintViewSet, QualityImprovementPlanViewSet,
)
from .roster_api import (
    DutyRosterViewSet,
    LeaveRequestViewSet,
    OvertimeRecordViewSet,
    PerformanceAppraisalViewSet,
    PerformanceAuditViewSet,
    ResearchOutputViewSet,
    TeachingActivityViewSet,
    SatisfactionSurveyViewSet,
    PerformanceIncidentViewSet,
)

router = DefaultRouter()
router.register(r'rounds', WardRoundViewSet, basename='ward-round')
router.register(r'handovers', HandoverNoteViewSet, basename='handover-note')
router.register(r'grand-rounds', GrandRoundViewSet, basename='grand-round')
router.register(r'wards', WardViewSet, basename='ward')
router.register(r'beds', BedViewSet, basename='bed')
router.register(r'admissions', AdmissionManagementViewSet, basename='admission-management')
router.register(r'emergency-calls', EmergencyCallViewSet, basename='emergency-call')
router.register(r'ambulance-missions', AmbulanceMissionViewSet, basename='ambulance-mission')
router.register(r'referrals', ReferralRequestViewSet, basename='referral-request')
router.register(r'duty-rosters', DutyRosterViewSet, basename='duty-roster')
router.register(r'leave-requests', LeaveRequestViewSet, basename='leave-request')
router.register(r'overtime-records', OvertimeRecordViewSet, basename='overtime-record')
router.register(r'performance-appraisals', PerformanceAppraisalViewSet, basename='performance-appraisal')
router.register(r'performance-audits', PerformanceAuditViewSet, basename='performance-audit')
router.register(r'research-outputs', ResearchOutputViewSet, basename='research-output')
router.register(r'teaching-activities', TeachingActivityViewSet, basename='teaching-activity')
router.register(r'satisfaction-surveys', SatisfactionSurveyViewSet, basename='satisfaction-survey')
router.register(r'performance-incidents', PerformanceIncidentViewSet, basename='performance-incident')
router.register(r'emergency-bays', EmergencyBayViewSet, basename='emergency-bay')
router.register(r'ambulances', AmbulanceViewSet, basename='ambulance')
router.register(r'emergency-cases', EmergencyCaseViewSet, basename='emergency-case')
router.register(r'patient-feedback', PatientFeedbackViewSet, basename='patient-feedback')
router.register(r'patient-surveys', PatientSurveyViewSet, basename='patient-survey')
router.register(r'patient-complaints', PatientComplaintViewSet, basename='patient-complaint')
router.register(r'quality-improvement-plans', QualityImprovementPlanViewSet, basename='quality-improvement-plan')

urlpatterns = [
    path('', include(router.urls)),
]
