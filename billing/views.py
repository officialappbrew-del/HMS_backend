from rest_framework import viewsets
from .models import Invoice
from .serializers import InvoiceSerializer
from core.permissions import IsTenantAdmin


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsTenantAdmin]