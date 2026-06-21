from rest_framework import viewsets
from .models import Drug, Dispense
from .serializers import DrugSerializer, DispenseSerializer
from core.permissions import IsPharmacist


class DrugViewSet(viewsets.ModelViewSet):
    queryset = Drug.objects.all()
    serializer_class = DrugSerializer


class DispenseViewSet(viewsets.ModelViewSet):
    queryset = Dispense.objects.all()
    serializer_class = DispenseSerializer
    permission_classes = [IsPharmacist]