from rest_framework import serializers
from .models import Drug, Supplier, Sale, SaleItem, Dispense


class DrugSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drug
        fields = '__all__'
        read_only_fields = ['status', 'tenant']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'


class SaleItemSerializer(serializers.ModelSerializer):
    drug_name = serializers.CharField(source='drug.name', read_only=True)

    class Meta:
        model = SaleItem
        fields = '__all__'
        read_only_fields = ['total_price']

    def validate(self, attrs):
        if attrs.get('unit_price') is not None and attrs.get('quantity') is not None:
            expected_total = attrs['unit_price'] * attrs['quantity']
            if attrs.get('total_price') and abs(attrs['total_price'] - expected_total) > 0.01:
                raise serializers.ValidationError({
                    'total_price': f'Total price must equal unit_price × quantity ({expected_total}).'
                })
        return attrs


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    sold_by_name = serializers.CharField(source='sold_by.get_full_name', read_only=True)
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)

    class Meta:
        model = Sale
        fields = '__all__'
        read_only_fields = ['sold_at']


class SaleCreateSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)

    class Meta:
        model = Sale
        fields = ['patient', 'payment_method', 'payment_status', 'status', 'discount', 'tax', 'notes', 'items']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        sale = Sale.objects.create(**validated_data)
        for item_data in items_data:
            SaleItem.objects.create(sale=sale, **item_data)
        return sale


class DispenseSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    drug_name = serializers.CharField(source='drug.name', read_only=True)
    dispensed_by_name = serializers.CharField(source='dispensed_by.get_full_name', read_only=True)

    class Meta:
        model = Dispense
        fields = '__all__'
        read_only_fields = ['total_price', 'dispensed_date', 'dispensed_by', 'tenant']

    def validate(self, attrs):
        prescription = attrs.get('prescription')
        if prescription:
            if prescription.status != 'prescribed':
                raise serializers.ValidationError({'prescription': 'Only prescribed prescriptions can be dispensed.'})
            if attrs.get('patient') and attrs['patient'].id != prescription.patient_id:
                raise serializers.ValidationError({'patient': 'Patient must match the prescription.'})
            drug = attrs.get('drug')
            prescribed_name = prescription.drug_name.lower()
            drug_names = {name.lower() for name in (drug.name, drug.generic_name, drug.brand_name) if name}
            if drug and prescribed_name not in drug_names:
                raise serializers.ValidationError({'drug': 'Selected inventory drug does not match the prescription.'})
            if not attrs.get('patient'):
                attrs['patient'] = prescription.patient
            requested_quantity = attrs.get('quantity') or 0
            already_dispensed = sum(item.quantity for item in prescription.dispenses.all())
            if already_dispensed + requested_quantity > prescription.quantity:
                raise serializers.ValidationError({'quantity': 'Quantity exceeds the remaining prescribed amount.'})
        if attrs.get('unit_price') is not None and attrs.get('quantity') is not None:
            expected_total = attrs['unit_price'] * attrs['quantity']
            if attrs.get('total_price') and abs(attrs['total_price'] - expected_total) > 0.01:
                raise serializers.ValidationError({
                    'total_price': f'Total price must equal unit_price × quantity ({expected_total}).'
                })
        return attrs
