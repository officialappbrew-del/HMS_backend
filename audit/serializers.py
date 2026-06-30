from rest_framework import serializers
from .models import ClinicalAudit, QualityIndicator, PeerReview, MortalityReview, ComplianceScore


class ClinicalAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalAudit
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class QualityIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityIndicator
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class PeerReviewSerializer(serializers.ModelSerializer):
    audit_title = serializers.CharField(source='audit.title', read_only=True)

    class Meta:
        model = PeerReview
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class MortalityReviewSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)

    class Meta:
        model = MortalityReview
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ComplianceScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceScore
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
