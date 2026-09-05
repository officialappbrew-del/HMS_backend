from decimal import Decimal
from rest_framework import serializers

from .models import (Account, Asset, JournalEntry, JournalLine, PurchaseOrder, PurchaseOrderLine,
                     TaxConfiguration, Vendor, VendorPayment)


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'
        read_only_fields = ['tenant']


class JournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'debit', 'credit', 'reference']

    def validate(self, attrs):
        if (attrs.get('debit', Decimal('0')) > 0) == (attrs.get('credit', Decimal('0')) > 0):
            raise serializers.ValidationError('Each journal line must have either a debit or a credit.')
        return attrs


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)

    class Meta:
        model = JournalEntry
        fields = '__all__'
        read_only_fields = ['tenant', 'created_by', 'approved_by']

    def validate(self, attrs):
        lines = attrs.get('lines', [])
        if not lines:
            raise serializers.ValidationError({'lines': 'At least two journal lines are required.'})
        debit = sum((line.get('debit', Decimal('0')) for line in lines), Decimal('0'))
        credit = sum((line.get('credit', Decimal('0')) for line in lines), Decimal('0'))
        if debit != credit:
            raise serializers.ValidationError({'lines': 'Total debits must equal total credits.'})
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop('lines')
        entry = JournalEntry.objects.create(**validated_data)
        JournalLine.objects.bulk_create([JournalLine(entry=entry, **line) for line in lines])
        return entry


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = '__all__'
        read_only_fields = ['tenant']


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = '__all__'
        read_only_fields = ['order']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = '__all__'
        read_only_fields = ['tenant', 'subtotal', 'tax_total', 'total_amount']

    def create(self, validated_data):
        lines = validated_data.pop('lines')
        order = PurchaseOrder.objects.create(**validated_data)
        subtotal = Decimal('0')
        tax_total = Decimal('0')
        for line in lines:
            item_total = line['quantity'] * line['unit_price']
            tax = item_total * line.get('tax_rate', Decimal('0')) / 100
            PurchaseOrderLine.objects.create(order=order, **line)
            subtotal += item_total
            tax_total += tax
        order.subtotal, order.tax_total, order.total_amount = subtotal, tax_total, subtotal + tax_total
        order.save(update_fields=['subtotal', 'tax_total', 'total_amount', 'updated_at'])
        return order


class VendorPaymentSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)

    class Meta:
        model = VendorPayment
        fields = '__all__'
        read_only_fields = ['tenant', 'net_payable', 'approved_by']

    def validate(self, attrs):
        attrs['net_payable'] = attrs.get('total_amount', 0) - attrs.get('tds_amount', 0) - attrs.get('discount_amount', 0)
        if attrs['net_payable'] < 0:
            raise serializers.ValidationError({'net_payable': 'Deductions cannot exceed the payment amount.'})
        return attrs


class AssetSerializer(serializers.ModelSerializer):
    annual_depreciation = serializers.ReadOnlyField()

    class Meta:
        model = Asset
        fields = '__all__'
        read_only_fields = ['tenant']


class TaxConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxConfiguration
        fields = '__all__'
        read_only_fields = ['tenant']
