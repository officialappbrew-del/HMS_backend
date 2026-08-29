from django.db import transaction
from django.db.models import Count, F, Sum, ExpressionWrapper, DecimalField
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.permissions import IsClinicalStaff, IsDoctorOrNurse
from core.views import TenantScopedModelViewSet
from patients.models import Patient
from ward_rounds.models import Ward, Bed
from .models import (
    IPDStay, IPDProgressNote, IntakeOutput, NursingCarePlan,
    MedicationAdministration, IPDTransfer, IPDDischarge,
    IPDClinicalRecord, IPDCharge, IPDWaitlist,
)
from .serializers import (
    IPDStaySerializer, IPDProgressNoteSerializer, IntakeOutputSerializer,
    NursingCarePlanSerializer, MedicationAdministrationSerializer,
    IPDTransferSerializer, IPDDischargeSerializer, IPDClinicalRecordSerializer,
    IPDChargeSerializer, IPDWaitlistSerializer,
)


def tenant_user(request):
    return getattr(request.user, 'tenant_user', None)


class IPDStayViewSet(TenantScopedModelViewSet):
    queryset = IPDStay.objects.select_related('patient', 'ward', 'bed', 'admitting_doctor')
    serializer_class = IPDStaySerializer
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        patient_id = self.request.query_params.get('patient_id')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        user = tenant_user(self.request)
        tenant = self.get_tenant()
        data = serializer.validated_data
        patient = data['patient']
        if patient.tenant_id != tenant.id:
            raise PermissionDenied('Patient does not belong to this tenant.')
        bed = data.get('bed')
        if bed:
            bed = Bed.objects.select_for_update().get(pk=bed.pk, tenant=tenant)
            if bed.status not in {Bed.Status.AVAILABLE, Bed.Status.RESERVED}:
                raise serializers.ValidationError({'bed': 'Bed is not available.'})
            if IPDStay.objects.filter(bed=bed, status__in=['admitted', 'pre_admission']).exists():
                raise serializers.ValidationError({'bed': 'Bed already has an active allocation.'})
        stay = serializer.save(tenant=tenant, admitting_doctor=data.get('admitting_doctor') or user)
        if stay.bed_id:
            stay.bed.status = Bed.Status.OCCUPIED
            stay.bed.patient = patient
            stay.bed.save(update_fields=['status', 'patient', 'updated_at'])
        stay.status = IPDStay.Status.ADMITTED if stay.bed_id else IPDStay.Status.WAITING
        stay.admitted_at = timezone.now() if stay.status == IPDStay.Status.ADMITTED else None
        stay.save(update_fields=['status', 'admitted_at', 'updated_at'])
        if stay.status == IPDStay.Status.WAITING:
            IPDWaitlist.objects.create(
                stay=stay,
                requested_ward_type=stay.ward.ward_type if stay.ward else 'any',
                priority='urgent' if stay.emergency else 'normal',
            )

    @action(detail=False, methods=['get'])
    def census(self, request):
        stays = self.get_queryset().filter(status=IPDStay.Status.ADMITTED)
        return Response({
            'total': stays.count(),
            'by_ward': list(stays.values('ward__ward_name').annotate(count=Count('id')).order_by('ward__ward_name')),
            'patients': IPDStaySerializer(stays, many=True).data,
        })

    @action(detail=False, methods=['get'])
    def reports(self, request):
        queryset = self.get_queryset()
        discharged = queryset.filter(status__in=[IPDStay.Status.DISCHARGED, IPDStay.Status.DECEASED])
        readmissions = queryset.filter(patient_id__in=queryset.values('patient_id')).values('patient_id').annotate(count=Count('id')).filter(count__gt=1).count()
        return Response({
            'census': queryset.filter(status=IPDStay.Status.ADMITTED).count(),
            'mortality': queryset.filter(status=IPDStay.Status.DECEASED).count(),
            'readmission_patients': readmissions,
            'discharged': discharged.count(),
            'average_length_of_stay': sum((stay.discharged_at - stay.admitted_at).total_seconds() / 86400 for stay in discharged if stay.admitted_at and stay.discharged_at) / discharged.filter(admitted_at__isnull=False, discharged_at__isnull=False).count() if discharged.filter(admitted_at__isnull=False, discharged_at__isnull=False).exists() else 0,
            'by_ward': list(queryset.filter(status=IPDStay.Status.ADMITTED).values('ward__ward_name').annotate(count=Count('id'))),
        })

    @action(detail=False, methods=['post'], url_path='allocate-waitlist')
    def allocate_waitlist(self, request):
        waitlist = get_object_or_404(IPDWaitlist.objects.select_related('stay'), pk=request.data.get('waitlist_id'), stay__tenant=self.get_tenant())
        bed = get_object_or_404(Bed.objects.select_for_update(), pk=request.data.get('bed_id'), tenant=self.get_tenant())
        if bed.status != Bed.Status.AVAILABLE:
            return Response({'detail': 'Bed is no longer available.'}, status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            bed.status = Bed.Status.OCCUPIED
            bed.patient = waitlist.stay.patient
            bed.save(update_fields=['status', 'patient', 'updated_at'])
            waitlist.stay.bed = bed
            waitlist.stay.ward = bed.ward
            waitlist.stay.status = IPDStay.Status.ADMITTED
            waitlist.stay.admitted_at = timezone.now()
            waitlist.stay.save(update_fields=['bed', 'ward', 'status', 'admitted_at', 'updated_at'])
            waitlist.delete()
        return Response(IPDStaySerializer(waitlist.stay).data)

    @action(detail=False, methods=['get'])
    def bed_availability(self, request):
        beds = Bed.objects.filter(tenant=self.get_tenant()).select_related('ward', 'patient')
        return Response({
            'total': beds.count(),
            'available': beds.filter(status=Bed.Status.AVAILABLE).count(),
            'occupied': beds.filter(status=Bed.Status.OCCUPIED).count(),
            'cleaning': beds.filter(status=Bed.Status.UNDER_CLEANING).count(),
            'maintenance': beds.filter(status=Bed.Status.MAINTENANCE).count(),
            'beds': [{
                'id': bed.id, 'bed_id': bed.bed_id, 'bed_number': bed.bed_number,
                'ward_id': bed.ward_id, 'ward_name': bed.ward.ward_name,
                'status': bed.status, 'patient_id': bed.patient_id,
                'patient_name': bed.patient.get_full_name() if bed.patient else None,
            } for bed in beds],
        })

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        stay = self.get_object()
        user = tenant_user(request)
        to_bed = get_object_or_404(Bed.objects.select_for_update(), pk=request.data.get('to_bed'), tenant=self.get_tenant())
        reason = str(request.data.get('reason', '')).strip()
        if not reason:
            return Response({'reason': 'Transfer reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if to_bed.status != Bed.Status.AVAILABLE:
            return Response({'to_bed': 'Destination bed is not available.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            to_bed = Bed.objects.select_for_update().get(pk=to_bed.pk)
            if to_bed.status != Bed.Status.AVAILABLE:
                return Response({'to_bed': 'Destination bed was taken. Refresh and retry.'}, status=status.HTTP_409_CONFLICT)
            old_bed = Bed.objects.select_for_update().filter(pk=stay.bed_id).first()
            transfer = IPDTransfer.objects.create(stay=stay, from_ward=stay.ward, from_bed=old_bed, to_ward=to_bed.ward, to_bed=to_bed, reason=reason, escort_details=request.data.get('escort_details', ''), transferred_by=user)
            if old_bed:
                old_bed.status = Bed.Status.UNDER_CLEANING
                old_bed.patient = None
                old_bed.save(update_fields=['status', 'patient', 'updated_at'])
            to_bed.status = Bed.Status.OCCUPIED
            to_bed.patient = stay.patient
            to_bed.save(update_fields=['status', 'patient', 'updated_at'])
            stay.ward = to_bed.ward
            stay.bed = to_bed
            stay.save(update_fields=['ward', 'bed', 'updated_at'])
        return Response({'transfer_id': transfer.id, 'stay': IPDStaySerializer(stay).data})

    @action(detail=True, methods=['post'])
    def discharge(self, request, pk=None):
        stay = self.get_object()
        if stay.status != IPDStay.Status.ADMITTED:
            return Response({'detail': 'Only admitted patients can be discharged.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = IPDDischargeSerializer(data={**request.data, 'stay': stay.pk}, context={'request': request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            discharge = serializer.save(prepared_by=tenant_user(request))
            stay.status = IPDStay.Status.DISCHARGED
            stay.discharged_at = timezone.now()
            stay.save(update_fields=['status', 'discharged_at', 'updated_at'])
            if stay.bed_id:
                Bed.objects.filter(pk=stay.bed_id).update(status=Bed.Status.UNDER_CLEANING, patient=None, updated_at=timezone.now())
        return Response(IPDDischargeSerializer(discharge).data, status=status.HTTP_201_CREATED)


class StayChildViewSet(TenantScopedModelViewSet):
    stay_field = 'stay'
    tenant_field = 'stay__tenant'
    permission_classes = [IsClinicalStaff]

    def get_queryset(self):
        return super().get_queryset().filter(stay__tenant=self.get_tenant()).select_related('stay', 'stay__patient')

    def perform_create(self, serializer):
        stay = get_object_or_404(IPDStay, pk=serializer.validated_data['stay'].pk, tenant=self.get_tenant())
        serializer.save(stay=stay)


class IPDProgressNoteViewSet(StayChildViewSet):
    queryset = IPDProgressNote.objects.all()
    serializer_class = IPDProgressNoteSerializer

    def perform_create(self, serializer):
        serializer.save(author=tenant_user(self.request))


class IntakeOutputViewSet(StayChildViewSet):
    queryset = IntakeOutput.objects.all()
    serializer_class = IntakeOutputSerializer

    def perform_create(self, serializer):
        serializer.save(recorded_by=tenant_user(self.request))


class NursingCarePlanViewSet(StayChildViewSet):
    queryset = NursingCarePlan.objects.all()
    serializer_class = NursingCarePlanSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=tenant_user(self.request))


class MedicationAdministrationViewSet(StayChildViewSet):
    queryset = MedicationAdministration.objects.all()
    serializer_class = MedicationAdministrationSerializer

    @action(detail=True, methods=['post'])
    def administer(self, request, pk=None):
        entry = self.get_object()
        serializer = self.get_serializer(entry, data={**request.data, 'status': request.data.get('status', 'given')}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(administered_by=tenant_user(request), administered_at=timezone.now())
        return Response(serializer.data)


class IPDTransferViewSet(StayChildViewSet):
    queryset = IPDTransfer.objects.all()
    serializer_class = IPDTransferSerializer


class IPDDischargeViewSet(StayChildViewSet):
    queryset = IPDDischarge.objects.all()
    serializer_class = IPDDischargeSerializer


class IPDClinicalRecordViewSet(StayChildViewSet):
    queryset = IPDClinicalRecord.objects.all()
    serializer_class = IPDClinicalRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        record_type = self.request.query_params.get('record_type')
        return queryset.filter(record_type=record_type) if record_type else queryset

    def perform_create(self, serializer):
        serializer.save(created_by=tenant_user(self.request))

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        record = self.get_object()
        record.status = 'completed'
        record.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(record).data)


class IPDChargeViewSet(StayChildViewSet):
    queryset = IPDCharge.objects.all()
    serializer_class = IPDChargeSerializer

    def perform_create(self, serializer):
        serializer.save(posted_by=tenant_user(self.request))

    @action(detail=False, methods=['get'])
    def report(self, request):
        queryset = self.get_queryset()
        return Response({
            'total': sum((charge.total for charge in queryset), 0),
            'by_category': list(queryset.values('category').annotate(total=Sum(ExpressionWrapper(F('quantity') * F('unit_price'), output_field=DecimalField(max_digits=12, decimal_places=2))))),
            'charges': IPDChargeSerializer(queryset, many=True).data,
        })


class IPDWaitlistViewSet(StayChildViewSet):
    queryset = IPDWaitlist.objects.all()
    serializer_class = IPDWaitlistSerializer
