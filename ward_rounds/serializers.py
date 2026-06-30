from rest_framework import serializers
from django.utils import timezone
from .models import WardRound, HandoverNote, GrandRound


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
