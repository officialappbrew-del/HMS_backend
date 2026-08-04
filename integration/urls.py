from django.urls import path

from .views import FHIRIntegrationViewSet, HL7IntegrationAPIView, IntegrationClientCreateAPIView, IntegrationMessageListAPIView

fhir_view = FHIRIntegrationViewSet.as_view({
    'get': 'list',
    'post': 'create',
    'head': 'list',
})

fhir_patient_view = FHIRIntegrationViewSet.as_view({
    'get': 'retrieve',
})

urlpatterns = [
    path('clients/', IntegrationClientCreateAPIView.as_view(), name='integration-client-create'),
    path('messages/', IntegrationMessageListAPIView.as_view(), name='integration-messages'),
    path('fhir/', fhir_view, name='fhir-integration'),
    path('fhir/metadata/', FHIRIntegrationViewSet.capability_statement, name='fhir-capability-statement'),
    path('fhir/patient/<int:pk>/', fhir_patient_view, name='fhir-patient'),
    path('hl7/message/', HL7IntegrationAPIView.as_view(), name='hl7-message'),
]
