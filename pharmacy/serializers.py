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
        read_only_fields = ['total_price', 'dispensed_date', 'dispensed_by']

    def validate(self, attrs):
        if attrs.get('unit_price') is not None and attrs.get('quantity') is not None:
            expected_total = attrs['unit_price'] * attrs['quantity']
            if attrs.get('total_price') and abs(attrs['total_price'] - expected_total) > 0.01:
                raise serializers.ValidationError({
                    'total_price': f'Total price must equal unit_price × quantity ({expected_total}).'
                })
        return attrs