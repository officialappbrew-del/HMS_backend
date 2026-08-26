from rest_framework import serializers
from .models import Invoice, InvoiceItem, Payment, InsuranceClaim, BillingAuditLog


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'item_type', 'description', 'quantity', 'unit_price', 
                  'tax_rate', 'discount_amount', 'line_total', 'drug_id', 'service_id']
        read_only_fields = ['id']


class PaymentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    
    class Meta:
        model = Payment
        fields = ['id', 'payment_number', 'payment_date', 'amount', 'payment_method',
                  'transaction_reference', 'received_by', 'notes', 'status',
                  'patient_name', 'invoice_number', 'invoice', 'patient', 'tenant',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'payment_number', 'payment_date', 'created_at', 'updated_at']


class InsuranceClaimSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    
    class Meta:
        model = InsuranceClaim
        fields = ['id', 'claim_number', 'claim_date', 'insurance_provider', 'policy_number',
                  'claimed_amount', 'approved_amount', 'rejected_amount', 'status',
                  'nhis_claim_number', 'nhis_status', 'submitted_date', 'processed_date',
                  'paid_date', 'notes', 'rejection_reason', 'supporting_documents',
                  'patient_name', 'invoice_number', 'invoice', 'patient', 'tenant',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'claim_number', 'claim_date', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    items = InvoiceItemSerializer(many=True, required=False)
    payments = PaymentSerializer(many=True, read_only=True)
    claims = InsuranceClaimSerializer(source='insurance_claims', many=True, read_only=True)
    
    class Meta:
        model = Invoice
        fields = ['id', 'invoice_number', 'invoice_date', 'due_date', 'patient', 'patient_name',
                  'visit', 'subtotal', 'tax_amount', 'discount_amount', 'total_amount',
                  'amount_paid', 'balance_due', 'status', 'insurance_covered', 'insurance_amount',
                  'patient_amount', 'nhis_claim_number', 'nhis_status', 'notes', 'created_by',
                  'tenant', 'items', 'payments', 'claims', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'invoice_number', 'invoice_date', 'created_at', 'updated_at', 'is_active']
    
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        invoice = Invoice.objects.create(**validated_data)
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        return invoice
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=instance, **item_data)
        return instance


class BillingAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingAuditLog
        fields = ['id', 'invoice', 'action', 'description', 'user', 'ip_address', 'created_at']
        read_only_fields = ['id', 'created_at']


class InvoiceSummarySerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    
    class Meta:
        model = Invoice
        fields = ['id', 'invoice_number', 'invoice_date', 'due_date', 'patient_name',
                  'total_amount', 'amount_paid', 'balance_due', 'status', 'nhis_status']
