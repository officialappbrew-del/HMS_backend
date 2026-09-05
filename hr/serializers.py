from rest_framework import serializers

from tenants.models import TenantUser
from .models import AttendanceRecord, LeaveApplication, PayrollLine, PayrollRun, SalaryStructure


class EmployeeSummarySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = TenantUser
        fields = ['id', 'employee_id', 'name', 'email', 'role', 'department', 'designation', 'employment_status']

    def get_name(self, obj):
        return obj.get_full_name()


class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = '__all__'
        read_only_fields = ['tenant', 'approved_by']


class LeaveApplicationSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = LeaveApplication
        fields = '__all__'
        read_only_fields = ['tenant', 'total_days', 'reviewed_by', 'review_reason']

    def validate(self, attrs):
        if attrs['end_date'] < attrs['start_date']:
            raise serializers.ValidationError({'end_date': 'End date must be on or after start date.'})
        attrs['total_days'] = (attrs['end_date'] - attrs['start_date']).days + 1
        return attrs


class SalaryStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryStructure
        fields = '__all__'
        read_only_fields = ['tenant']


class PayrollLineSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = PayrollLine
        fields = '__all__'
        read_only_fields = ['run']


class PayrollRunSerializer(serializers.ModelSerializer):
    lines = PayrollLineSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollRun
        fields = '__all__'
        read_only_fields = ['tenant', 'created_by', 'total_gross', 'total_deductions', 'total_net']
