from rest_framework import serializers
from .models import Budget, Forecast, Grant, BudgetVariance, BudgetReport


class BudgetSerializer(serializers.ModelSerializer):
    variance = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    
    class Meta:
        model = Budget
        fields = ['id', 'department', 'category', 'year', 'period', 'amount', 'utilized',
                  'variance', 'description', 'status', 'approval_required', 'approved_by',
                  'start_date', 'end_date', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant']


class ForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Forecast
        fields = ['id', 'category', 'period', 'year', 'predicted_amount', 'confidence_level',
                  'assumptions', 'methodology', 'accuracy', 'actual_amount',
                  'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant']


class GrantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grant
        fields = ['id', 'name', 'donor', 'amount', 'start_date', 'end_date', 'purpose',
                  'conditions', 'contact_person', 'reporting_frequency', 'status', 'utilized',
                  'last_report_date', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant']


class BudgetVarianceSerializer(serializers.ModelSerializer):
    budget_name = serializers.CharField(source='budget.__str__', read_only=True)
    
    class Meta:
        model = BudgetVariance
        fields = ['id', 'budget', 'budget_name', 'period', 'year', 'planned_amount',
                  'actual_amount', 'variance_amount', 'variance_percentage', 'notes',
                  'alert_triggered', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant']


class BudgetReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetReport
        fields = ['id', 'report_type', 'title', 'period_start', 'period_end',
                  'generated_by', 'file_path', 'summary', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'tenant']
