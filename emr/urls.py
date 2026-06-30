from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    MedicalRecordViewSet, ProgressNoteViewSet,
    ClinicalDocumentViewSet, ProblemListViewSet, AllergyViewSet
)

router = DefaultRouter()
router.register(r'medical-records', MedicalRecordViewSet, basename='medical-record')
router.register(r'progress-notes', ProgressNoteViewSet, basename='progress-note')
router.register(r'clinical-documents', ClinicalDocumentViewSet, basename='clinical-document')
router.register(r'problem-list', ProblemListViewSet, basename='problem-list')
router.register(r'allergies', AllergyViewSet, basename='allergy')

medical_record_list = MedicalRecordViewSet.as_view({'get': 'list', 'post': 'create'})
medical_record_detail = MedicalRecordViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})
medical_record_sign = MedicalRecordViewSet.as_view({'post': 'sign'})

progress_note_list = ProgressNoteViewSet.as_view({'get': 'list', 'post': 'create'})
progress_note_detail = ProgressNoteViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})
progress_note_sign = ProgressNoteViewSet.as_view({'post': 'sign'})

clinical_document_list = ClinicalDocumentViewSet.as_view({'get': 'list', 'post': 'create'})
clinical_document_detail = ClinicalDocumentViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})

problem_list_list = ProblemListViewSet.as_view({'get': 'list', 'post': 'create'})
problem_list_detail = ProblemListViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})
problem_list_resolve = ProblemListViewSet.as_view({'post': 'resolve'})

allergy_list = AllergyViewSet.as_view({'get': 'list', 'post': 'create'})
allergy_detail = AllergyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})

urlpatterns = [
    path('medical-records/', medical_record_list, name='medical-record-list'),
    path('medical-records/<int:pk>/', medical_record_detail, name='medical-record-detail'),
    path('medical-records/<int:pk>/sign/', medical_record_sign, name='medical-record-sign'),

    path('progress-notes/', progress_note_list, name='progress-note-list'),
    path('progress-notes/<int:pk>/', progress_note_detail, name='progress-note-detail'),
    path('progress-notes/<int:pk>/sign/', progress_note_sign, name='progress-note-sign'),

    path('clinical-documents/', clinical_document_list, name='clinical-document-list'),
    path('clinical-documents/<int:pk>/', clinical_document_detail, name='clinical-document-detail'),

    path('problem-list/', problem_list_list, name='problem-list-list'),
    path('problem-list/<int:pk>/', problem_list_detail, name='problem-list-detail'),
    path('problem-list/<int:pk>/resolve/', problem_list_resolve, name='problem-list-resolve'),

    path('allergies/', allergy_list, name='allergy-list'),
    path('allergies/<int:pk>/', allergy_detail, name='allergy-detail'),
]
