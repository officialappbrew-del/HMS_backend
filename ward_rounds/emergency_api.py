from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets

from core.permissions import IsClinicalStaff
from .models import EmergencyCall, AmbulanceMission, ReferralRequest
from .serializers import EmergencyCallSerializer, AmbulanceMissionSerializer, ReferralRequestSerializer


class EmergencyCallViewSet(viewsets.ModelViewSet):
    queryset = EmergencyCall.objects.all()
    serializer_class = EmergencyCallSerializer
    permission_classes = [IsClinicalStaff]

    @action(detail=True, methods=['post'], url_path='dispatch')
    def dispatch_emergency_call(self, request, pk=None):
        emergency_call = self.get_object()
        emergency_call.status = EmergencyCall.EmergencyStatus.DISPATCHED
        emergency_call.dispatched_ambulance = request.data.get('ambulanceId') or request.data.get('ambulance_id') or ''
        emergency_call.response_time = int(request.data.get('responseTime') or 0)
        emergency_call.save(update_fields=['status', 'dispatched_ambulance', 'response_time', 'updated_at'])
        return Response(EmergencyCallSerializer(emergency_call).data)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        emergency_call = self.get_object()
        status_value = request.data.get('status') or request.data.get('newStatus') or ''
        if status_value:
            emergency_call.status = status_value
            if status_value == EmergencyCall.EmergencyStatus.COMPLETED:
                emergency_call.response_time = int(request.data.get('responseTime') or emergency_call.response_time)
            emergency_call.save(update_fields=['status', 'response_time', 'updated_at'])
        return Response(EmergencyCallSerializer(emergency_call).data)


class AmbulanceMissionViewSet(viewsets.ModelViewSet):
    queryset = AmbulanceMission.objects.all()
    serializer_class = AmbulanceMissionSerializer
    permission_classes = [IsClinicalStaff]

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        mission = self.get_object()
        status_value = request.data.get('status') or request.data.get('newStatus') or ''
        if status_value:
            mission.status = status_value
            if status_value == AmbulanceMission.MissionStatus.COMPLETED:
                mission.completed_at = request.data.get('completedAt') or timezone.now()
                mission.outcome = request.data.get('outcome') or 'Completed'
            mission.save(update_fields=['status', 'completed_at', 'outcome', 'updated_at'])
        return Response(AmbulanceMissionSerializer(mission).data)


class ReferralRequestViewSet(viewsets.ModelViewSet):
    queryset = ReferralRequest.objects.all()
    serializer_class = ReferralRequestSerializer
    permission_classes = [IsClinicalStaff]

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        referral = self.get_object()
        referral.status = ReferralRequest.ReferralStatus.APPROVED
        referral.save(update_fields=['status', 'updated_at'])
        return Response(ReferralRequestSerializer(referral).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        referral = self.get_object()
        referral.status = ReferralRequest.ReferralStatus.COMPLETED
        referral.arrival_time = request.data.get('arrivalTime') or timezone.now()
        referral.outcome = request.data.get('outcome') or 'Completed'
        referral.save(update_fields=['status', 'arrival_time', 'outcome', 'updated_at'])
        return Response(ReferralRequestSerializer(referral).data)
