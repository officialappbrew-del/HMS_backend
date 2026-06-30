from rest_framework import serializers
from .models import MedicalRecord, ProgressNote, ClinicalDocument, ProblemList, Allergy


class MedicalRecordSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    primary_doctor_name = serializers.CharField(source='primary_doctor.get_full_name', read_only=True)
    
    class Meta:
        model = MedicalRecord
        fields = '__all__'
        read_only_fields = ['record_number', 'created_at', 'updated_at', 'tenant']


class ProgressNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    medical_record_number = serializers.CharField(source='medical_record.record_number', read_only=True)
    
    class Meta:
        model = ProgressNote
        fields = '__all__'
        read_only_fields = ['tenant', 'author', 'created_at', 'signed_at']
        extra_kwargs = {
            'medical_record': {'required': False, 'allow_null': True},
        }


class ClinicalDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicalDocument
        fields = '__all__'
        read_only_fields = ['created_at', 'tenant']
    
    def get_file_url_display(self, obj):
        if obj.file:
            return obj.file.url
        return obj.file_url


class ProblemListSerializer(serializers.ModelSerializer):
    diagnosed_by_name = serializers.CharField(source='diagnosed_by.get_full_name', read_only=True)
    
    class Meta:
        model = ProblemList
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'resolved_at', 'tenant']


class AllergySerializer(serializers.ModelSerializer):
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)
    
    class Meta:
        model = Allergy
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'tenant']
