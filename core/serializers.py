from rest_framework import serializers
from .models import (
    Country, State, LGA, FacilityType, Specialization,
    Language, NotificationTemplate, SystemSetting, AuditLog
)


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = '__all__'


class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)
    
    class Meta:
        model = State
        fields = '__all__'


class LGASerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source='state.name', read_only=True)
    country_name = serializers.CharField(source='state.country.name', read_only=True)
    
    class Meta:
        model = LGA
        fields = '__all__'


class FacilityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacilityType
        fields = '__all__'


class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = '__all__'


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = '__all__'


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = '__all__'


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = '__all__'
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Convert value based on data_type
        if instance.data_type == 'integer':
            data['value'] = int(instance.value)
        elif instance.data_type == 'boolean':
            data['value'] = instance.value.lower() == 'true'
        elif instance.data_type == 'float':
            data['value'] = float(instance.value)
        elif instance.data_type == 'json':
            import json
            data['value'] = json.loads(instance.value)
        return data
    
    def to_internal_value(self, data):
        # Validate and convert value based on data_type
        value = data.get('value')
        data_type = data.get('data_type')
        
        if data_type == 'integer':
            try:
                data['value'] = str(int(value))
            except (ValueError, TypeError):
                raise serializers.ValidationError({
                    'value': 'Must be a valid integer'
                })
        elif data_type == 'boolean':
            if isinstance(value, bool):
                data['value'] = str(value).lower()
            elif isinstance(value, str):
                if value.lower() not in ['true', 'false']:
                    raise serializers.ValidationError({
                        'value': 'Must be true or false'
                    })
                data['value'] = value.lower()
            else:
                raise serializers.ValidationError({
                    'value': 'Must be a boolean'
                })
        elif data_type == 'float':
            try:
                data['value'] = str(float(value))
            except (ValueError, TypeError):
                raise serializers.ValidationError({
                    'value': 'Must be a valid float'
                })
        elif data_type == 'json':
            import json
            try:
                json.dumps(value)  # Validate JSON
                data['value'] = json.dumps(value)
            except (TypeError, ValueError):
                raise serializers.ValidationError({
                    'value': 'Must be valid JSON'
                })
        
        return super().to_internal_value(data)


class AuditLogSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = '__all__'
        read_only_fields = ['timestamp', 'ip_address', 'user_agent']