from rest_framework import serializers

from .models import (
    IPDStay, IPDProgressNote, IntakeOutput, NursingCarePlan,
    MedicationAdministration, IPDTransfer, IPDDischarge,
    IPDClinicalRecord, IPDCharge, IPDWaitlist,
)


class IPDStaySerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_mrn = serializers.CharField(source='patient.mrn', read_only=True)
    ward_name = serializers.CharField(source='ward.ward_name', read_only=True)
    bed_number = serializers.IntegerField(source='bed.bed_number', read_only=True)
    doctor_name = serializers.CharField(source='admitting_doctor.get_full_name', read_only=True)

    class Meta:
        model = IPDStay
        fields = '__all__'
        read_only_fields = ['tenant', 'admission_number', 'admitted_at', 'discharged_at', 'created_at', 'updated_at']


class IPDProgressNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)

    class Meta:
        model = IPDProgressNote
        fields = '__all__'
        read_only_fields = ['author', 'created_at', 'updated_at']


class IntakeOutputSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = IntakeOutput
        fields = '__all__'
        read_only_fields = ['recorded_by', 'created_at', 'updated_at']


class NursingCarePlanSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = NursingCarePlan
        fields = '__all__'
        read_only_fields = ['created_by', 'completed_at', 'created_at', 'updated_at']


class MedicationAdministrationSerializer(serializers.ModelSerializer):
    administered_by_name = serializers.CharField(source='administered_by.get_full_name', read_only=True)

    class Meta:
        model = MedicationAdministration
        fields = '__all__'
        read_only_fields = ['administered_by', 'administered_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        if attrs.get('status') in {'held', 'refused', 'omitted'} and not attrs.get('reason'):
            raise serializers.ValidationError({'reason': 'A reason is required when a dose is not given.'})
        return attrs


class IPDTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPDTransfer
        fields = '__all__'
        read_only_fields = ['from_ward', 'from_bed', 'transferred_by', 'transferred_at', 'created_at', 'updated_at']


class IPDDischargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPDDischarge
        fields = '__all__'
        read_only_fields = ['prepared_by', 'completed_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        if not attrs.get('summary_signed'):
            raise serializers.ValidationError({'summary_signed': 'The discharge summary must be signed before discharge.'})
        if not attrs.get('billing_cleared'):
            raise serializers.ValidationError({'billing_cleared': 'Billing clearance is required before discharge.'})
        if not attrs.get('belongings_returned'):
            raise serializers.ValidationError({'belongings_returned': 'Confirm that patient belongings were returned.'})
        return attrs


class IPDClinicalRecordSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = IPDClinicalRecord
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class IPDChargeSerializer(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()
    posted_by_name = serializers.CharField(source='posted_by.get_full_name', read_only=True)

    class Meta:
        model = IPDCharge
        fields = '__all__'
        read_only_fields = ['posted_by', 'created_at', 'updated_at']

    def get_total(self, obj):
        return obj.total


class IPDWaitlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPDWaitlist
        fields = '__all__'
        read_only_fields = ['notified_at', 'created_at', 'updated_at']
