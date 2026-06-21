from rest_framework import serializers
from .models import LabTest, LabOrder, LabResult, NCDCReport, InstrumentMaintenance


class LabTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = '__all__'


class LabOrderSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    test_name = serializers.CharField(source='test.name', read_only=True)
    ordered_by_name = serializers.CharField(source='ordered_by.get_full_name', read_only=True)
    
    class Meta:
        model = LabOrder
        fields = '__all__'


class LabResultSerializer(serializers.ModelSerializer):
    test_name = serializers.CharField(source='order.test.name', read_only=True)
    patient_name = serializers.CharField(source='order.patient.get_full_name', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    
    class Meta:
        model = LabResult
        fields = '__all__'


class LabResultCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabResult
        fields = ['order', 'value', 'value_numeric', 'units', 'reference_range', 
                  'reference_low', 'reference_high', 'result_notes', 'instrument_reading']
    
    def create(self, validated_data):
        order = validated_data.get('order')
        value = validated_data.get('value', '')
        
        # Try to parse numeric value
        if not validated_data.get('value_numeric'):
            try:
                validated_data['value_numeric'] = float(value)
            except (ValueError, TypeError):
                pass
        
        # Set reference values from test if not provided
        if not validated_data.get('reference_low') or not validated_data.get('reference_high'):
            test = order.test
            if not validated_data.get('reference_range'):
                validated_data['reference_range'] = test.reference_range
        
        # Check for critical values
        if validated_data.get('value_numeric'):
            if test.critical_low and validated_data['value_numeric'] < float(test.critical_low):
                validated_data['is_critical'] = True
                validated_data['flag'] = 'LL'
            elif test.critical_high and validated_data['value_numeric'] > float(test.critical_high):
                validated_data['is_critical'] = True
                validated_data['flag'] = 'HH'
            elif validated_data.get('reference_low') and validated_data['value_numeric'] < validated_data['reference_low']:
                validated_data['flag'] = 'L'
            elif validated_data.get('reference_high') and validated_data['value_numeric'] > validated_data['reference_high']:
                validated_data['flag'] = 'H'
        
        return super().create(validated_data)


class NCDCReportSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    
    class Meta:
        model = NCDCReport
        fields = '__all__'


class NCDCReportSubmitSerializer(serializers.Serializer):
    report_type = serializers.ChoiceField(choices=[
        ('lassa_fever', 'Lassa Fever'),
        ('cholera', 'Cholera'),
        ('yellow_fever', 'Yellow Fever'),
        ('measles', 'Measles'),
        ('meningitis', 'Meningitis'),
        ('covid19', 'COVID-19'),
        ('other', 'Other Notifiable Disease'),
    ])
    case_count = serializers.IntegerField(min_value=1)
    lga = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True)


class InstrumentMaintenanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstrumentMaintenance
        fields = '__all__'


class CriticalResultSerializer(serializers.Serializer):
    """Serializer for critical results response"""
    id = serializers.IntegerField()
    order_id = serializers.IntegerField()
    patient_id = serializers.IntegerField()
    patient_name = serializers.CharField()
    patient_identifier = serializers.CharField()
    test_name = serializers.CharField()
    value = serializers.CharField()
    reference_range = serializers.CharField()
    critical_since = serializers.CharField()
    ordered_by = serializers.CharField()
    status = serializers.ChoiceField(choices=['awaiting', 'notified', 'acknowledged'])
