from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    IPDStayViewSet, IPDProgressNoteViewSet, IntakeOutputViewSet,
    NursingCarePlanViewSet, MedicationAdministrationViewSet,
    IPDTransferViewSet, IPDDischargeViewSet, IPDClinicalRecordViewSet,
    IPDChargeViewSet, IPDWaitlistViewSet,
)

router = DefaultRouter()
router.register('stays', IPDStayViewSet, basename='ipd-stay')
router.register('progress-notes', IPDProgressNoteViewSet, basename='ipd-progress-note')
router.register('intake-output', IntakeOutputViewSet, basename='ipd-intake-output')
router.register('care-plans', NursingCarePlanViewSet, basename='ipd-care-plan')
router.register('mar', MedicationAdministrationViewSet, basename='ipd-mar')
router.register('transfers', IPDTransferViewSet, basename='ipd-transfer')
router.register('discharges', IPDDischargeViewSet, basename='ipd-discharge')
router.register('clinical-records', IPDClinicalRecordViewSet, basename='ipd-clinical-record')
router.register('charges', IPDChargeViewSet, basename='ipd-charge')
router.register('waitlist', IPDWaitlistViewSet, basename='ipd-waitlist')

urlpatterns = [path('', include(router.urls))]