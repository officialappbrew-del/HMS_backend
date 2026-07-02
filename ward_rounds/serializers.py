from rest_framework import serializers
from django.utils import timezone
from .models import WardRound, HandoverNote, GrandRound, Ward, Bed, Admission


class WardSerializer(serializers.ModelSerializer):
    wardId = serializers.CharField(source='ward_id')
    wardName = serializers.CharField(source='ward_name')
    wardType = serializers.CharField(source='ward_type')
    totalBeds = serializers.IntegerField(source='total_beds')
    staffCount = serializers.IntegerField(source='staff_count')

    class Meta:
        model = Ward
        fields = [
            'id', 'wardId', 'wardName', 'wardType', 'floor', 'supervisor',
            'staffCount', 'totalBeds', 'notes', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_active']


class BedSerializer(serializers.ModelSerializer):
    bedId = serializers.CharField(source='bed_id')
    bedNumber = serializers.IntegerField(source='bed_number')
    bedType = serializers.CharField(source='bed_type')
    isPrivate = serializers.BooleanField(source='is_private')
    cleaningStatus = serializers.CharField(source='cleaning_status')
    lastCleaned = serializers.DateTimeField(source='last_cleaned', required=False, allow_null=True)
    lastTurnover = serializers.DateTimeField(source='last_turnover', required=False, allow_null=True)
    wardId = serializers.CharField(source='ward.ward_id', read_only=True)
    patientId = serializers.CharField(source='patient.hospital_number', read_only=True)

    class Meta:
        model = Bed
        fields = [
            'id', 'bedId', 'bedNumber', 'bedType', 'status', 'patientId',
            'isPrivate', 'cleaningStatus', 'lastCleaned', 'lastTurnover',
            'wardId', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_active']

    def validate(self, attrs):
        ward_id = self.initial_data.get('wardId') or self.initial_data.get('ward_id')
        if ward_id and 'ward' not in attrs:
            request = self.context.get('request')
            tenant = None
            if request is not None and hasattr(request.user, 'tenant_user') and request.user.tenant_user:
                tenant = request.user.tenant_user.tenant

            queryset = Ward.objects.filter(ward_id=ward_id)
            if tenant is not None:
                queryset = queryset.filter(tenant=tenant)

            try:
                ward = queryset.get()
            except Ward.DoesNotExist:
                raise serializers.ValidationError({'wardId': 'Ward not found for this tenant.'})
            attrs['ward'] = ward
        return attrs

    def create(self, validated_data):
        ward = validated_data.pop('ward', None)
        if ward is not None:
            validated_data['ward'] = ward
        return super().create(validated_data)


class WardRoundSerializer(serializers.ModelSerializer):
    roundId = serializers.SerializerMethodField()
    patientsList = serializers.JSONField(source='patients_list', required=False, default=list)
    teamMembers = serializers.JSONField(source='team_members', required=False, default=list)
    expectedDuration = serializers.IntegerField(source='expected_duration', required=False, default=120)
    actualDuration = serializers.IntegerField(source='actual_duration', required=False, allow_null=True)
    startTime = serializers.DateTimeField(source='start_time', required=False, allow_null=True)
    completedTime = serializers.DateTimeField(source='completed_time', required=False, allow_null=True)
    cancellationReason = serializers.CharField(source='cancellation_reason', required=False, allow_blank=True, default='')
    consultantSpecialty = serializers.CharField(source='consultant_specialty', required=False, allow_blank=True, default='')
    wardName = serializers.CharField(source='ward_name')
    wardId = serializers.CharField(source='ward_id')
    roundType = serializers.CharField(source='round_type', required=False, default='Daily Ward Round')
    consultant = serializers.CharField()
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    date = serializers.DateTimeField(required=False, default=timezone.now)

    class Meta:
        model = WardRound
        fields = [
            'id', 'roundId', 'tenant', 'wardId', 'wardName', 'roundType', 'status',
            'date', 'time', 'consultant', 'consultantSpecialty', 'teamMembers',
            'patientsList', 'notes', 'expectedDuration', 'actualDuration',
            'startTime', 'completedTime', 'cancellationReason',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_active']

    def get_roundId(self, obj):
        return f"WR{str(obj.id).zfill(3)}"


class HandoverNoteSerializer(serializers.ModelSerializer):
    handoverId = serializers.SerializerMethodField()
    shiftFrom = serializers.CharField(source='shift_from')
    shiftTo = serializers.CharField(source='shift_to')
    handoverOfficer = serializers.CharField(source='handover_officer')
    receivingOfficer = serializers.CharField(source='receiving_officer')
    criticallySevere = serializers.JSONField(source='critically_severe', required=False, default=list)
    recentAdmissions = serializers.JSONField(source='recent_admissions', required=False, default=list)
    pendingProcedures = serializers.JSONField(source='pending_procedures', required=False, default=list)
    pendingDischarges = serializers.JSONField(source='pending_discharges', required=False, default=list)
    wardName = serializers.CharField(source='ward_name')
    wardId = serializers.CharField(source='ward_id')
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    date = serializers.DateTimeField(required=False, default=timezone.now)

    class Meta:
        model = HandoverNote
        fields = [
            'id', 'handoverId', 'tenant', 'wardId', 'wardName', 'date',
            'shiftFrom', 'shiftTo', 'handoverOfficer', 'receivingOfficer',
            'criticallySevere', 'recentAdmissions', 'pendingProcedures',
            'pendingDischarges', 'notes',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_active']

    def get_handoverId(self, obj):
        return f"HO{str(obj.id).zfill(3)}"


class AdmissionSerializer(serializers.ModelSerializer):
    admissionId = serializers.SerializerMethodField()
    patientId = serializers.CharField(source='patient_id', required=False, allow_blank=True)
    patientName = serializers.CharField(source='patient_name', required=False, allow_blank=True)
    requestId = serializers.CharField(source='request_id', read_only=True)
    requestDate = serializers.DateTimeField(source='request_date', read_only=True)
    preferredWardType = serializers.CharField(source='preferred_ward_type', required=False, allow_blank=True, default='')
    consultantName = serializers.CharField(source='consultant_name', required=False, allow_blank=True, default='')
    consultantSpecialty = serializers.CharField(source='consultant_specialty', required=False, allow_blank=True, default='')
    wardId = serializers.CharField(source='ward_id', required=False, allow_blank=True, default='')
    wardName = serializers.CharField(source='ward_id', read_only=True)
    bedId = serializers.CharField(source='bed_id', required=False, allow_blank=True, default='')
    expectedStay = serializers.IntegerField(source='expected_stay', required=False, default=0)
    plannedDischargeDate = serializers.DateTimeField(source='planned_discharge_date', required=False, allow_null=True)
    dateOfAdmission = serializers.DateTimeField(source='date_of_admission', required=False, allow_null=True)
    dischargeDate = serializers.DateTimeField(source='discharge_date', required=False, allow_null=True)
    actualStay = serializers.IntegerField(source='actual_stay', required=False, allow_null=True)
    rejectionReason = serializers.CharField(source='rejection_reason', required=False, allow_blank=True, default='')
    approvalDate = serializers.DateTimeField(required=False, allow_null=True, write_only=True)
    source = serializers.CharField(required=False, allow_blank=True, default='Direct Admission')
    diagnosis = serializers.CharField(required=False, allow_blank=True, default='')
    priority = serializers.CharField(required=False, allow_blank=True, default='Medium')
    dischargeSummary = serializers.JSONField(source='discharge_summary', required=False, default=dict)
    transferHistory = serializers.JSONField(source='transfer_history', required=False, default=list)

    class Meta:
        model = Admission
        fields = [
            'id', 'admissionId', 'patientId', 'patientName', 'requestId', 'requestDate', 'source', 'diagnosis',
            'preferredWardType', 'priority', 'status', 'rejectionReason', 'notes', 'wardId', 'wardName', 'bedId',
            'consultantName', 'consultantSpecialty', 'expectedStay', 'plannedDischargeDate',
            'actualStay', 'dateOfAdmission', 'dischargeDate', 'approvalDate', 'dischargeSummary', 'transferHistory',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'requestId', 'requestDate', 'created_at', 'updated_at', 'is_active']

    def get_admissionId(self, obj):
        return f"ADM{str(obj.id).zfill(3)}"

    def to_internal_value(self, data):
        normalized_data = dict(data)
        if 'patient_id' in normalized_data and 'patientId' not in normalized_data:
            normalized_data['patientId'] = normalized_data['patient_id']
        if 'patient_name' in normalized_data and 'patientName' not in normalized_data:
            normalized_data['patientName'] = normalized_data['patient_name']
        if 'preferred_ward_type' in normalized_data and 'preferredWardType' not in normalized_data:
            normalized_data['preferredWardType'] = normalized_data['preferred_ward_type']
        return super().to_internal_value(normalized_data)

    def create(self, validated_data):
        tenant = self.context.get('tenant')
        if tenant is not None:
            validated_data['tenant'] = tenant
        admission = Admission.objects.create(**validated_data)
        admission.request_id = f"REQ{admission.id}"
        admission.save(update_fields=['request_id'])
        return admission


class GrandRoundSerializer(serializers.ModelSerializer):
    grandRoundId = serializers.SerializerMethodField()
    caseStudies = serializers.JSONField(source='case_studies', required=False, allow_null=True, default=list)
    expectedAttendees = serializers.IntegerField(source='expected_attendees', required=False, default=0)
    targetAudience = serializers.CharField(source='target_audience', required=False, allow_blank=True, default='')
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = GrandRound
        fields = [
            'id', 'grandRoundId', 'tenant', 'date', 'time', 'status',
            'topic', 'presenter', 'location', 'targetAudience', 'caseStudies',
            'expectedAttendees', 'notes',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_active']

    def get_grandRoundId(self, obj):
        return f"GR{str(obj.id).zfill(3)}"
