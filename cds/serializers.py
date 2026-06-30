from rest_framework import serializers
from .models import DrugInteraction, AllergyCheck, DosingGuideline, ClinicalGuideline, RiskAssessment, PatientAlert


class DrugInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrugInteraction
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class AllergyCheckSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)

    class Meta:
        model = AllergyCheck
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class DosingGuidelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DosingGuideline
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class ClinicalGuidelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalGuideline
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class RiskAssessmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    calculated_by_name = serializers.CharField(source='calculated_by.get_full_name', read_only=True)

    class Meta:
        model = RiskAssessment
        fields = '__all__'
        read_only_fields = ['calculated_at']


class PatientAlertSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)

    class Meta:
        model = PatientAlert
        fields = '__all__'
        read_only_fields = ['created_at']
