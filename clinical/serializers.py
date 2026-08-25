from rest_framework import serializers
from .models import ConsultationNote, Prescription, VitalSign, EarlyWarningScore, VitalSignAlert


class PrescriptionInteractionCheckSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(required=False)
    drug_names = serializers.ListField(child=serializers.CharField(), required=False)
    prescription_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class MedicationHistorySerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(required=False)
    medications = serializers.ListField(child=serializers.DictField(), required=False)
    warnings = serializers.ListField(child=serializers.DictField(), required=False)


class ConsultationNoteSerializer(serializers.ModelSerializer):
    """Serializer for ConsultationNote model."""
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.get_full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    
    class Meta:
        model = ConsultationNote
        fields = '__all__'
        read_only_fields = ['tenant', 'created_at', 'updated_at']


class PrescriptionSerializer(serializers.ModelSerializer):
    """Serializer for Prescription model."""
    route = serializers.CharField(required=False)
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    prescribed_by_name = serializers.CharField(source='prescribed_by.get_full_name', read_only=True)
    dispensed_by_name = serializers.CharField(source='dispensed_by.get_full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    patient_mrn = serializers.CharField(source='patient.mrn', read_only=True)
    patient_hospital_number = serializers.CharField(source='patient.hospital_number', read_only=True)
    
    class Meta:
        model = Prescription
        fields = '__all__'
        read_only_fields = ['prescribed_date', 'patient', 'tenant', 'prescribed_by', 'dispensed_by', 'dispensed_date']

    def validate_route(self, value):
        route = str(value).strip().lower()
        valid_routes = {choice[0] for choice in Prescription._meta.get_field('route').choices}
        if route not in valid_routes:
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return route


class VitalSignSerializer(serializers.ModelSerializer):
    """Serializer for VitalSign model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)
    blood_pressure_display = serializers.SerializerMethodField()
    blood_pressure_category = serializers.SerializerMethodField()
    early_warning_scores = serializers.SerializerMethodField()
    
    class Meta:
        model = VitalSign
        fields = '__all__'
        read_only_fields = ['tenant', 'recorded_by', 'recorded_at', 'bmi']
    
    def get_blood_pressure_display(self, obj):
        if obj.blood_pressure_systolic and obj.blood_pressure_diastolic:
            return f"{obj.blood_pressure_systolic}/{obj.blood_pressure_diastolic}"
        return None
    
    def get_blood_pressure_category(self, obj):
        return obj.get_blood_pressure_category()

    def get_early_warning_scores(self, obj):
        return EarlyWarningScoreSerializer(obj.early_warning_scores.all(), many=True).data


class EarlyWarningScoreSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    calculated_by_name = serializers.CharField(source='calculated_by.get_full_name', read_only=True)
    visit_number = serializers.CharField(source='visit.visit_number', read_only=True)
    
    class Meta:
        model = EarlyWarningScore
        fields = '__all__'
        read_only_fields = ['calculated_at']


class VitalSignAlertSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    acknowledged_by_name = serializers.CharField(source='acknowledged_by.get_full_name', read_only=True)
    resolved_by_name = serializers.CharField(source='resolved_by.get_full_name', read_only=True)
    
    class Meta:
        model = VitalSignAlert
        fields = '__all__'
        read_only_fields = ['created_at']