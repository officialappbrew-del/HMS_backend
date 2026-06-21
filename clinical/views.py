from rest_framework import viewsets
from .models import ConsultationNote, Prescription, VitalSign
from .serializers import ConsultationNoteSerializer, PrescriptionSerializer, VitalSignSerializer
from core.permissions import IsDoctor, IsNurse


class ConsultationNoteViewSet(viewsets.ModelViewSet):
    queryset = ConsultationNote.objects.all()
    serializer_class = ConsultationNoteSerializer
    permission_classes = [IsDoctor]


class PrescriptionViewSet(viewsets.ModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [IsDoctor]


class VitalSignViewSet(viewsets.ModelViewSet):
    queryset = VitalSign.objects.all()
    serializer_class = VitalSignSerializer
    permission_classes = [IsDoctor | IsNurse]