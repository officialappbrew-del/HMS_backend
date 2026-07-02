from rest_framework import serializers
from django.utils import timezone

from .models import ConsentRecord, DataSubjectRequest, DataBreach, NDPRAuditLog, ComplianceReport


class ConsentRecordSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(source='patient_id')
    patientName = serializers.CharField(source='patient_name')
    consentType = serializers.CharField(source='consent_type')
    dataCategories = serializers.JSONField(source='data_categories', default=list)
    retentionPeriod = serializers.CharField(source='retention_period', required=False, allow_blank=True)
    thirdParties = serializers.JSONField(source='third_parties', default=list)
    consentMethod = serializers.CharField(source='consent_method')
    witnessName = serializers.CharField(source='witness_name', required=False, allow_blank=True)
    expiryDate = serializers.DateField(source='expiry_date', required=False, allow_null=True)
    withdrawnAt = serializers.DateTimeField(source='withdrawn_at', required=False, allow_null=True)
    withdrawalReason = serializers.CharField(source='withdrawal_reason', required=False, allow_blank=True)
    recordedBy = serializers.PrimaryKeyRelatedField(source='recorded_by', read_only=True)

    class Meta:
        model = ConsentRecord
        fields = [
            'id', 'patientId', 'patientName', 'consentType', 'purpose', 'dataCategories',
            'retentionPeriod', 'thirdParties', 'consentMethod', 'witnessName',
            'status', 'expiryDate', 'withdrawnAt', 'withdrawalReason', 'recordedBy',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'status', 'tenant']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        user = self.context.get('request').user if self.context.get('request') else None
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        validated_data['tenant'] = tenant
        validated_data['recorded_by'] = tenant_user
        return super().create(validated_data)

    def validate(self, attrs):
        consent_type = attrs.get('consent_type')
        purpose = attrs.get('purpose')
        if not purpose or len(purpose.strip()) < 10:
            raise serializers.ValidationError({'purpose': 'Purpose must be at least 10 characters.'})
        if consent_type == ConsentRecord.ConsentType.THIRD_PARTY:
            third_parties = attrs.get('third_parties', [])
            if not third_parties:
                raise serializers.ValidationError({'third_parties': 'Third party sharing requires specifying third parties.'})
        return attrs


class DataSubjectRequestSerializer(serializers.ModelSerializer):
    requesterType = serializers.CharField(source='requester_type')
    requesterName = serializers.CharField(source='requester_name')
    requesterContact = serializers.CharField(source='requester_contact')
    requestType = serializers.CharField(source='request_type')
    dataCategories = serializers.JSONField(source='data_categories', default=list)
    urgency = serializers.CharField(source='urgency')
    identityVerification = serializers.CharField(source='identity_verification', required=False, allow_blank=True)
    submittedAt = serializers.DateTimeField(source='submitted_at', read_only=True)
    processedAt = serializers.DateTimeField(source='processed_at', read_only=True)
    processingTime = serializers.CharField(source='processing_time', read_only=True)
    completedAt = serializers.DateTimeField(source='completed_at', read_only=True)
    reviewedBy = serializers.PrimaryKeyRelatedField(source='reviewed_by', read_only=True)

    class Meta:
        model = DataSubjectRequest
        fields = [
            'id', 'requesterType', 'requesterName', 'requesterContact', 'requestType',
            'dataCategories', 'reason', 'urgency', 'identityVerification', 'status',
            'submittedAt', 'processedAt', 'processingTime', 'response', 'completedAt', 'reviewedBy',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'status', 'tenant']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        validated_data['tenant'] = tenant
        return super().create(validated_data)

    def validate(self, attrs):
        request_type = attrs.get('request_type')
        data_categories = attrs.get('data_categories', [])
        if not data_categories:
            raise serializers.ValidationError({'data_categories': 'At least one data category must be specified.'})
        if request_type == DataSubjectRequest.RequestType.ERASURE and len(data_categories) > 1:
            raise serializers.ValidationError({'data_categories': 'Erasure requests should specify a single data category.'})
        return attrs


class DataBreachSerializer(serializers.ModelSerializer):
    breachType = serializers.CharField(source='breach_type')
    affectedData = serializers.JSONField(source='affected_data', default=list)
    affectedIndividuals = serializers.IntegerField(source='affected_individuals')
    breachDate = serializers.DateTimeField(source='breach_date')
    discoveryDate = serializers.DateTimeField(source='discovery_date')
    containmentActions = serializers.CharField(source='containment_actions')
    impactAssessment = serializers.CharField(source='impact_assessment', required=False, allow_blank=True)
    reportedToNITDA = serializers.BooleanField(source='reported_to_nitda')
    nitdaReportDate = serializers.DateTimeField(source='nitda_report_date', required=False, allow_null=True)
    notificationSent = serializers.BooleanField(source='notification_sent')
    notificationsSentCount = serializers.IntegerField(source='notifications_sent_count', read_only=True)
    responseTimeHours = serializers.FloatField(source='response_time_hours', read_only=True)
    investigationFindings = serializers.CharField(source='investigation_findings', required=False, allow_blank=True)
    preventiveActions = serializers.CharField(source='preventive_actions', required=False, allow_blank=True)
    reportedBy = serializers.PrimaryKeyRelatedField(source='reported_by', read_only=True)

    class Meta:
        model = DataBreach
        fields = [
            'id', 'breachType', 'affectedData', 'affectedIndividuals', 'breachDate', 'discoveryDate',
            'description', 'containmentActions', 'impactAssessment', 'severity', 'status',
            'reportedToNITDA', 'nitdaReportDate', 'notificationSent', 'notificationsSentCount',
            'responseTime_hours', 'investigationFindings', 'preventiveActions', 'reportedBy',
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant', 'response_time_hours']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        user = self.context.get('request').user if self.context.get('request') else None
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        validated_data['tenant'] = tenant
        validated_data['reported_by'] = tenant_user
        if validated_data.get('discovery_date') and validated_data.get('breach_date'):
            delta = validated_data['discovery_date'] - validated_data['breach_date']
            validated_data['response_time_hours'] = delta.total_seconds() / 3600.0
        return super().create(validated_data)


class NDPRAuditLogSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    actionType = serializers.CharField(source='action')
    resourceType = serializers.CharField(source='resource_type')
    resourceId = serializers.CharField(source='resource_id')
    patientId = serializers.CharField(source='patient_id')
    ipAddress = serializers.IPAddressField(source='ip_address')
    userAgent = serializers.CharField(source='user_agent')

    class Meta:
        model = NDPRAuditLog
        fields = [
            'id', 'actionType', 'description', 'resourceType', 'resourceId',
            'patientId', 'ipAddress', 'userAgent', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_active', 'tenant']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        user = self.context.get('request').user if self.context.get('request') else None
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        validated_data['tenant'] = tenant
        validated_data['user'] = tenant_user
        if user:
            validated_data['ip_address'] = self.context.get('request').META.get('REMOTE_ADDR')
            validated_data['user_agent'] = self.context.get('request').META.get('HTTP_USER_AGENT', '')
        return super().create(validated_data)


class ComplianceReportSerializer(serializers.ModelSerializer):
    reportType = serializers.CharField(source='report_type')
    periodStart = serializers.DateField(source='period_start')
    periodEnd = serializers.DateField(source='period_end')
    generatedBy = serializers.PrimaryKeyRelatedField(source='generated_by', read_only=True)
    filePath = serializers.CharField(source='file_path', read_only=True)

    class Meta:
        model = ComplianceReport
        fields = [
            'id', 'reportType', 'title', 'periodStart', 'periodEnd', 'status',
            'generatedBy', 'filePath', 'summary', 'metadata', 'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant', 'generated_by', 'file_path']

    def create(self, validated_data):
        tenant = validated_data.pop('tenant', None) or self.context.get('tenant')
        user = self.context.get('request').user if self.context.get('request') else None
        tenant_user = getattr(user, 'tenant_user', None) if user else None
        validated_data['tenant'] = tenant
        validated_data['generated_by'] = tenant_user
        return super().create(validated_data)
