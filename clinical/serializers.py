from rest_framework import serializers
from .models import ConsultationNote, Prescription, VitalSign


class ConsultationNoteSerializer(serializers.ModelSerializer):
    """Serializer for ConsultationNote model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.get_full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    
    class Meta:
        model = ConsultationNote
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class PrescriptionSerializer(serializers.ModelSerializer):
    """Serializer for Prescription model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    prescribed_by_name = serializers.CharField(source='prescribed_by.get_full_name', read_only=True)
    dispensed_by_name = serializers.CharField(source='dispensed_by.get_full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    
    class Meta:
        model = Prescription
        fields = '__all__'
        read_only_fields = ['prescribed_date']


class VitalSignSerializer(serializers.ModelSerializer):
    """Serializer for VitalSign model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)
    blood_pressure_display = serializers.SerializerMethodField()
    blood_pressure_category = serializers.SerializerMethodField()
    
    class Meta:
        model = VitalSign
        fields = '__all__'
        read_only_fields = ['recorded_at', 'bmi']
    
    def get_blood_pressure_display(self, obj):
        if obj.blood_pressure_systolic and obj.blood_pressure_diastolic:
            return f"{obj.blood_pressure_systolic}/{obj.blood_pressure_diastolic}"
        return None
    
    def get_blood_pressure_category(self, obj):
        return obj.get_blood_pressure_category()