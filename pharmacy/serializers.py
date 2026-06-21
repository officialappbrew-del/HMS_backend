from rest_framework import serializers
from .models import Drug, Dispense


class DrugSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drug
        fields = '__all__'


class DispenseSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    drug_name = serializers.CharField(source='drug.name', read_only=True)
    dispensed_by_name = serializers.CharField(source='dispensed_by.get_full_name', read_only=True)
    
    class Meta:
        model = Dispense
        fields = '__all__'