from rest_framework import serializers
from django.utils import timezone
from .models import (
    WardRound, HandoverNote, GrandRound, Ward, Bed, Admission, EmergencyCall,
    AmbulanceMission, ReferralRequest, DutyRoster, DutyAssignment, LeaveRequest,
    OvertimeRecord, PerformanceAppraisal, PerformanceAudit, ResearchOutput,
    TeachingActivity, SatisfactionSurvey, PerformanceIncident
)


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


class DutyAssignmentSerializer(serializers.ModelSerializer):
    assignmentId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    dutyType = serializers.CharField(source='duty_type')
    startTime = serializers.TimeField(source='start_time', required=False, allow_null=True)
    endTime = serializers.TimeField(source='end_time', required=False, allow_null=True)

    class Meta:
        model = DutyAssignment
        fields = ['id', 'assignmentId', 'staffId', 'staffName', 'staffUserId', 'date', 'dutyType', 'startTime', 'endTime', 'notes']
        read_only_fields = ['id', 'assignmentId', 'staffUserId']


class DutyRosterSerializer(serializers.ModelSerializer):
    rosterId = serializers.CharField(source='roster_id', read_only=True)
    assignments = DutyAssignmentSerializer(many=True, required=False)

    class Meta:
        model = DutyRoster
        fields = ['id', 'rosterId', 'month', 'year', 'department', 'status', 'assignments', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'rosterId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data, **kwargs):
        assignments_data = validated_data.pop('assignments', [])
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        roster = DutyRoster.objects.create(tenant=tenant, **validated_data)
        for assignment_data in assignments_data:
            DutyAssignment.objects.create(roster=roster, **assignment_data)
        return roster


class LeaveRequestSerializer(serializers.ModelSerializer):
    leaveId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    leaveType = serializers.CharField(source='leave_type')
    startDate = serializers.DateField(source='start_date')
    endDate = serializers.DateField(source='end_date')
    approvedBy = serializers.CharField(source='approved_by', required=False, allow_blank=True)
    approvalDate = serializers.DateField(source='approval_date', required=False, allow_null=True)

    class Meta:
        model = LeaveRequest
        fields = ['id', 'leaveId', 'staffId', 'staffName', 'staffUserId', 'leaveType', 'startDate', 'endDate', 'reason', 'status', 'approvedBy', 'approvalDate', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'leaveId', 'staffUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return LeaveRequest.objects.create(tenant=tenant, **validated_data)


class OvertimeRecordSerializer(serializers.ModelSerializer):
    overtimeId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    hoursWorked = serializers.DecimalField(source='hours_worked', max_digits=5, decimal_places=2)
    approvalStatus = serializers.CharField(source='status', read_only=True)
    approvedBy = serializers.CharField(source='approved_by', required=False, allow_blank=True)
    approvalDate = serializers.DateField(source='approval_date', required=False, allow_null=True)

    class Meta:
        model = OvertimeRecord
        fields = ['id', 'overtimeId', 'staffId', 'staffName', 'staffUserId', 'date', 'hoursWorked', 'reason', 'approvalStatus', 'approvedBy', 'approvalDate', 'rate', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'overtimeId', 'staffUserId', 'approvalStatus', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return OvertimeRecord.objects.create(tenant=tenant, **validated_data)


class PerformanceAppraisalSerializer(serializers.ModelSerializer):
    appraisalId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    raterUserId = serializers.IntegerField(source='rater_user.id', read_only=True, required=False)
    appraisalYear = serializers.IntegerField(source='appraisal_year')
    clinicalExcellence = serializers.DecimalField(source='clinical_excellence', max_digits=3, decimal_places=2)
    patientCare = serializers.DecimalField(source='patient_care', max_digits=3, decimal_places=2)
    continuousLearning = serializers.DecimalField(source='continuous_learning', max_digits=3, decimal_places=2)
    overallComments = serializers.CharField(source='overall_comments', required=False, allow_blank=True)
    overallRating = serializers.DecimalField(source='rating', max_digits=3, decimal_places=2, required=False)
    comments = serializers.CharField(source='overall_comments', required=False, allow_blank=True)

    class Meta:
        model = PerformanceAppraisal
        fields = [
            'id', 'appraisalId', 'staffId', 'staffName', 'staffUserId', 'raterUserId', 'appraisalYear', 'period', 'rater', 'rating',
            'overallRating', 'clinicalExcellence', 'patientCare', 'teamwork', 'leadership', 'continuousLearning',
            'overallComments', 'comments', 'status', 'date', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'appraisalId', 'staffUserId', 'raterUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return PerformanceAppraisal.objects.create(tenant=tenant, **validated_data)


class PerformanceAuditSerializer(serializers.ModelSerializer):
    auditId = serializers.CharField(source='id', read_only=True)
    department = serializers.CharField()
    auditType = serializers.CharField(source='audit_type')
    auditor = serializers.CharField(required=False, allow_blank=True)
    auditorUserId = serializers.IntegerField(source='auditor_user.id', read_only=True, required=False)
    auditDate = serializers.DateField(source='audit_date')
    casesReviewed = serializers.IntegerField(source='cases_reviewed')
    complianceRate = serializers.CharField(source='compliance_rate', required=False, allow_blank=True)

    class Meta:
        model = PerformanceAudit
        fields = ['id', 'auditId', 'department', 'auditType', 'auditor', 'auditorUserId', 'auditDate', 'casesReviewed', 'complianceRate', 'findings', 'recommendations', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'auditId', 'auditorUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return PerformanceAudit.objects.create(tenant=tenant, **validated_data)


class ResearchOutputSerializer(serializers.ModelSerializer):
    researchId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    publicationTitle = serializers.CharField(source='title')
    publicationType = serializers.CharField(source='publication_type', required=False, allow_blank=True)
    journalName = serializers.CharField(source='journal_name', required=False, allow_blank=True)
    publicationDate = serializers.DateField(source='publication_date')
    citationCount = serializers.IntegerField(source='citation_count')

    class Meta:
        model = ResearchOutput
        fields = ['id', 'researchId', 'staffId', 'staffName', 'staffUserId', 'publicationTitle', 'publicationType', 'journalName', 'publicationDate', 'authors', 'status', 'citationCount', 'abstract', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'researchId', 'staffUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return ResearchOutput.objects.create(tenant=tenant, **validated_data)


class TeachingActivitySerializer(serializers.ModelSerializer):
    teachingId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    month = serializers.CharField()
    topic = serializers.CharField()
    hoursDelivered = serializers.IntegerField(source='hours_delivered')
    studentsCount = serializers.IntegerField(source='students_count')
    feedbackScore = serializers.DecimalField(source='feedback_score', max_digits=3, decimal_places=2)

    class Meta:
        model = TeachingActivity
        fields = ['id', 'teachingId', 'staffId', 'staffName', 'staffUserId', 'month', 'topic', 'hoursDelivered', 'studentsCount', 'feedbackScore', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'teachingId', 'staffUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return TeachingActivity.objects.create(tenant=tenant, **validated_data)


class SatisfactionSurveySerializer(serializers.ModelSerializer):
    satisfactionId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    surveyDate = serializers.DateField(source='survey_date')
    totalFeedback = serializers.IntegerField(source='total_feedback')
    averageScore = serializers.DecimalField(source='average_score', max_digits=3, decimal_places=2)
    clinicalCareScore = serializers.DecimalField(source='clinical_care', max_digits=3, decimal_places=2, required=False)
    communicationScore = serializers.DecimalField(source='communication', max_digits=3, decimal_places=2, required=False)
    responsivenessScore = serializers.DecimalField(source='responsiveness', max_digits=3, decimal_places=2, required=False)
    professionalismScore = serializers.DecimalField(source='professionalism', max_digits=3, decimal_places=2, required=False)
    overallScore = serializers.DecimalField(source='overall_satisfaction', max_digits=3, decimal_places=2, required=False)
    comments = serializers.JSONField(source='comments', required=False, default=list)

    class Meta:
        model = SatisfactionSurvey
        fields = ['id', 'satisfactionId', 'staffId', 'staffName', 'staffUserId', 'surveyDate', 'totalFeedback', 'averageScore', 'clinicalCareScore', 'communicationScore', 'responsivenessScore', 'professionalismScore', 'overallScore', 'comments', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'satisfactionId', 'staffUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return SatisfactionSurvey.objects.create(tenant=tenant, **validated_data)


class PerformanceIncidentSerializer(serializers.ModelSerializer):
    incidentId = serializers.CharField(source='id', read_only=True)
    staffId = serializers.CharField(source='staff_id')
    staffName = serializers.CharField(source='staff_name', required=False, allow_blank=True)
    staffUserId = serializers.IntegerField(source='staff_user.id', read_only=True, required=False)
    incidentType = serializers.CharField(source='incident_type')
    reportedDate = serializers.DateField(source='reported_date')
    investigationStatus = serializers.CharField(source='investigation_status')
    rootCauseAnalysis = serializers.CharField(source='root_cause_analysis', required=False, allow_blank=True)
    actionTaken = serializers.CharField(source='action_taken', required=False, allow_blank=True)

    class Meta:
        model = PerformanceIncident
        fields = ['id', 'incidentId', 'staffId', 'staffName', 'staffUserId', 'incidentType', 'reportedDate', 'description', 'severity', 'investigationStatus', 'rootCauseAnalysis', 'actionTaken', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'incidentId', 'staffUserId', 'created_at', 'updated_at', 'is_active']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        return PerformanceIncident.objects.create(tenant=tenant, **validated_data)


class EmergencyCallSerializer(serializers.ModelSerializer):
    callId = serializers.CharField(source='call_id', required=False, allow_blank=True)
    callerName = serializers.CharField(source='caller_name', required=False, allow_blank=True)
    callerPhone = serializers.CharField(source='caller_phone', required=False, allow_blank=True)
    incidentType = serializers.CharField(source='incident_type', required=False, allow_blank=True)
    incidentDescription = serializers.CharField(source='incident_description', required=False, allow_blank=True)
    patientName = serializers.CharField(source='patient_name', required=False, allow_blank=True)
    patientDetails = serializers.JSONField(source='patient_details', required=False, default=dict)
    incidentLocation = serializers.JSONField(source='incident_location', required=False, default=dict)
    dispatchedAmbulance = serializers.CharField(source='dispatched_ambulance', required=False, allow_blank=True)
    responseTime = serializers.IntegerField(source='response_time', required=False, default=0)

    class Meta:
        model = EmergencyCall
        fields = [
            'id', 'callId', 'callerName', 'callerPhone', 'severity', 'status', 'incidentType', 'incidentDescription',
            'patientName', 'patientDetails', 'incidentLocation', 'dispatchedAmbulance', 'responseTime', 'notes', 'communications',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active']


class AmbulanceMissionSerializer(serializers.ModelSerializer):
    missionId = serializers.CharField(source='mission_id', required=False, allow_blank=True)
    ambulanceId = serializers.CharField(source='ambulance_id', required=False, allow_blank=True)
    incidentType = serializers.CharField(source='incident_type', required=False, allow_blank=True)
    patientInfo = serializers.JSONField(source='patient_info', required=False, default=dict)
    pickupLocation = serializers.JSONField(source='pickup_location', required=False, default=dict)
    destination = serializers.JSONField(source='destination', required=False, default=dict)
    dispatchedAt = serializers.DateTimeField(source='dispatched_at', required=False)
    completedAt = serializers.DateTimeField(source='completed_at', required=False, allow_null=True)

    class Meta:
        model = AmbulanceMission
        fields = [
            'id', 'missionId', 'ambulanceId', 'incidentType', 'priority', 'status', 'patientInfo', 'pickupLocation',
            'destination', 'crew', 'notes', 'dispatchedAt', 'completedAt', 'outcome', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active']


class ReferralRequestSerializer(serializers.ModelSerializer):
    referralId = serializers.CharField(source='referral_id', required=False, allow_blank=True)
    patientName = serializers.CharField(source='patient_name', required=False, allow_blank=True)
    patientAge = serializers.IntegerField(source='patient_age', required=False, default=0)
    patientGender = serializers.CharField(source='patient_gender', required=False, allow_blank=True)
    referralType = serializers.CharField(source='referral_type', required=False, allow_blank=True)
    referralReason = serializers.CharField(source='referral_reason', required=False, allow_blank=True)
    referringFacility = serializers.JSONField(source='referring_facility', required=False, default=dict)
    receivingFacility = serializers.JSONField(source='receiving_facility', required=False, default=dict)
    ambulanceId = serializers.CharField(source='ambulance_id', required=False, allow_blank=True)
    referralDate = serializers.DateTimeField(source='referral_date', required=False)
    arrivalTime = serializers.DateTimeField(source='arrival_time', required=False, allow_null=True)
    isMedicalEvacuation = serializers.BooleanField(source='is_medical_evacuation', required=False, default=False)
    fundingSource = serializers.CharField(source='funding_source', required=False, allow_blank=True)
    originCountry = serializers.CharField(source='origin_country', required=False, allow_blank=True)
    destinationCountry = serializers.CharField(source='destination_country', required=False, allow_blank=True)
    transportMode = serializers.CharField(source='transport_mode', required=False, allow_blank=True)
    transferCompliance = serializers.JSONField(source='transfer_compliance', required=False, default=dict)

    class Meta:
        model = ReferralRequest
        fields = [
            'id', 'referralId', 'patientName', 'patientAge', 'patientGender', 'referralType', 'referralReason',
            'referringFacility', 'receivingFacility', 'status', 'ambulanceId', 'referralDate', 'arrivalTime', 'outcome',
            'notes', 'isMedicalEvacuation', 'fundingSource', 'originCountry', 'destinationCountry', 'transportMode', 'cost',
            'transferCompliance', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active']


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
