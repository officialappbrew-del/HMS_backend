from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
import re

from .models import (
    Patient, PatientVisit, PatientDocument,
    PatientAllergy, PatientMedication, Appointment,
    BulkPatientUpload, PatientMerge
)
from tenants.models import Tenant
from users.models import PasswordResetToken


class PatientSerializer(serializers.ModelSerializer):
    """Serializer for Patient model."""
    full_name = serializers.SerializerMethodField()
    age_display = serializers.SerializerMethodField()
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    password = serializers.CharField(write_only=True, required=False)
    hospital_number = serializers.CharField(required=False, allow_blank=True)
    mrn = serializers.CharField(required=False, read_only=True)
    dnr_order = serializers.BooleanField(required=False)
    dnr_order_reason = serializers.CharField(required=False, allow_blank=True)
    dnr_order_date = serializers.DateField(required=False, allow_null=True)
    login_id = serializers.CharField(required=False, allow_blank=True)
    preferred_language = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all(), required=False, allow_null=True)
    initial_charges = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)

    class Meta:
        model = Patient
        fields = '__all__'
        read_only_fields = ['registration_date', 'age', 'tenant', 'registered_by', 'mrn']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate_initial_charges(self, charges):
        allowed_types = {'consultation', 'drug', 'service', 'test', 'procedure', 'admission', 'other'}
        validated = []
        for index, charge in enumerate(charges):
            description = str(charge.get('description', '')).strip()
            if not description:
                raise serializers.ValidationError({index: ['Charge description is required.']})
            try:
                quantity = int(charge.get('quantity', 1))
                unit_price = Decimal(str(charge.get('unit_price', 0)))
            except (TypeError, ValueError, ArithmeticError):
                raise serializers.ValidationError({index: ['Quantity and unit price must be valid numbers.']})
            item_type = charge.get('item_type', 'service')
            if item_type not in allowed_types or quantity <= 0 or unit_price < 0:
                raise serializers.ValidationError({index: ['Charge type, quantity, and price are invalid.']})
            validated.append({
                'item_type': item_type,
                'description': description,
                'quantity': quantity,
                'unit_price': unit_price,
            })
        return validated

    def create(self, validated_data):
        initial_charges = validated_data.pop('initial_charges', [])
        password = validated_data.pop('password', None)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            tenant_user = getattr(request.user, 'tenant_user', None)
            if tenant_user is not None:
                validated_data['registered_by'] = tenant_user
                validated_data.setdefault('tenant', getattr(tenant_user, 'tenant', None))
        with transaction.atomic():
            patient = Patient.objects.create(**validated_data)
            if initial_charges:
                from billing.models import Invoice, InvoiceItem

                invoice = Invoice.objects.create(
                    tenant=patient.tenant,
                    patient=patient,
                    due_date=timezone.now(),
                    status='issued',
                    created_by=str(request.user) if request and request.user.is_authenticated else '',
                )
                subtotal = Decimal('0')
                for charge in initial_charges:
                    quantity = int(charge.get('quantity', 1))
                    unit_price = Decimal(str(charge.get('unit_price', 0)))
                    line_total = unit_price * quantity
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        item_type=charge.get('item_type', 'service'),
                        description=str(charge.get('description', '')).strip(),
                        quantity=quantity,
                        unit_price=unit_price,
                        line_total=line_total,
                    )
                    subtotal += line_total
                invoice.subtotal = subtotal
                invoice.total_amount = subtotal
                invoice.balance_due = subtotal
                invoice.patient_amount = subtotal
                invoice.save(update_fields=['subtotal', 'total_amount', 'balance_due', 'patient_amount', 'updated_at'])
        if password:
            patient.set_password(password)
            patient.save(update_fields=['password'])
        return patient

    def update(self, instance, validated_data):
        validated_data.pop('initial_charges', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_age_display(self, obj):
        return obj.get_age_display()

    def validate_email(self, value):
        if value and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', value):
            raise serializers.ValidationError("Invalid email format")
        return value

    def validate_date_of_birth(self, value):
        if value and value > timezone.now().date():
            raise serializers.ValidationError("Date of birth cannot be in the future")
        return value


class PatientLoginSerializer(serializers.Serializer):
    """Login serializer for patients using their generated login ID and password."""
    identifier = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, data):
        identifier = str(data.get('identifier') or '').strip()
        password = str(data.get('password') or '')

        patient = None

        if identifier:
            # Prefer MRN when identifiers overlap in legacy patient records.
            patient = Patient.objects.filter(mrn__iexact=identifier).first()
            if patient is None:
                patient = Patient.objects.filter(hospital_number__iexact=identifier).first()
            if patient is None:
                try:
                    patient = Patient.objects.get(login_id__iexact=identifier)
                except Patient.DoesNotExist:
                    try:
                        patient = Patient.objects.get(id=int(identifier))
                    except (Patient.DoesNotExist, ValueError):
                        patient = None

        if not patient:
            raise serializers.ValidationError("Invalid patient identifier or password.")

        # If the patient has not set a password yet, allow login using the MRN
        # (or hospital number/login ID) as the password fallback.
        if not patient.password:
            valid_fallbacks = {
                '',
            }
            normalized_fallbacks = {
                value.casefold() for value in (
                    patient.mrn,
                    patient.hospital_number,
                    patient.login_id,
                ) if value
            }
            if password.casefold() in valid_fallbacks or password.casefold() in normalized_fallbacks:
                data['patient'] = patient
                return data
            raise serializers.ValidationError(
                "This patient has no password set. Use the MRN as the password fallback."
            )

        if patient.check_password(password):
            data['patient'] = patient
            return data

        raise serializers.ValidationError("Invalid patient identifier or password.")


class PatientVisitSerializer(serializers.ModelSerializer):
    """Serializer for PatientVisit model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_mrn = serializers.CharField(source='patient.mrn', read_only=True)
    patient_hospital_number = serializers.CharField(source='patient.hospital_number', read_only=True)
    patient_gender = serializers.CharField(source='patient.gender', read_only=True)
    patient_age = serializers.IntegerField(source='patient.age', read_only=True)
    patient_insurance = serializers.CharField(source='patient.insurance_company', read_only=True)
    doctor_name = serializers.CharField(source='doctor.get_full_name', read_only=True)
    nurse_name = serializers.CharField(source='nurse.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    waiting_time = serializers.SerializerMethodField()

    class Meta:
        model = PatientVisit
        fields = '__all__'
        read_only_fields = ['visit_number', 'checkin_time']

    def get_waiting_time(self, obj):
        waiting = obj.get_waiting_time()
        if waiting:
            minutes = waiting.total_seconds() / 60
            return f"{int(minutes)} minutes"
        return None


class PatientDocumentSerializer(serializers.ModelSerializer):
    """Serializer for PatientDocument model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = PatientDocument
        fields = '__all__'
        read_only_fields = ['file_name', 'file_size', 'file_type', 'upload_date']

    def get_file_size_display(self, obj):
        file_size = obj.file_size
        if file_size < 1024:
            return f"{file_size} B"
        elif file_size < 1024 * 1024:
            return f"{file_size / 1024:.1f} KB"
        else:
            return f"{file_size / (1024 * 1024):.1f} MB"
        return None


class PatientAllergySerializer(serializers.ModelSerializer):
    """Serializer for PatientAllergy model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)

    class Meta:
        model = PatientAllergy
        fields = '__all__'


class PatientMedicationSerializer(serializers.ModelSerializer):
    """Serializer for PatientMedication model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    prescribed_by_name = serializers.CharField(source='prescribed_by.get_full_name', read_only=True)

    class Meta:
        model = PatientMedication
        fields = '__all__'


class AppointmentSerializer(serializers.ModelSerializer):
    """Serializer for Appointment model."""
    patient_name = serializers.CharField(source='patient.get_full_name', read_only=True)
    patient_mrn = serializers.CharField(source='patient.mrn', read_only=True)
    patient_hospital_number = serializers.CharField(source='patient.hospital_number', read_only=True)
    doctor_name = serializers.CharField(source='doctor.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    patient_phone = serializers.CharField(source='patient.phone', read_only=True)
    patient_email = serializers.CharField(source='patient.email', read_only=True)
    send_reminder = serializers.BooleanField(required=False, default=False, write_only=True)
    reminder_channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )
    preferred_channel = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Appointment
        fields = '__all__'
        read_only_fields = ['appointment_number', 'tenant']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Prefer the tenant-scoped user when available
            created_by = getattr(request.user, 'tenant_user', None)
            if created_by is not None:
                validated_data['created_by'] = created_by
        validated_data.pop('send_reminder', None)
        validated_data.pop('reminder_channels', None)
        validated_data.pop('preferred_channel', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Prefer the tenant-scoped user when available
            validated_data['updated_by'] = getattr(request.user, 'tenant_user', None) or request.user
        validated_data.pop('send_reminder', None)
        validated_data.pop('reminder_channels', None)
        validated_data.pop('preferred_channel', None)
        return super().update(instance, validated_data)


class PatientSearchSerializer(serializers.Serializer):
    """Serializer for patient search."""
    hospital_number = serializers.CharField(required=False)
    nhis_number = serializers.CharField(required=False)
    nin = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    email = serializers.CharField(required=False)


class PatientMergeSerializer(serializers.ModelSerializer):
    source_patient = PatientSerializer(read_only=True)
    survivor_patient = PatientSerializer(read_only=True)
    moved_record_count = serializers.SerializerMethodField()

    class Meta:
        model = PatientMerge
        fields = '__all__'

    def get_moved_record_count(self, obj):
        return len(obj.moved_records or [])


class PatientPasswordResetRequestSerializer(serializers.Serializer):
    """Request a password reset token for a patient."""
    identifier = serializers.CharField(required=True)
    
    def validate(self, data):
        identifier = data.get('identifier', '').strip()
        if not identifier:
            raise serializers.ValidationError({'identifier': 'Please enter your patient ID, hospital number, MRN, or email.'})
        return data


class PatientPasswordResetVerifySerializer(serializers.Serializer):
    """Verify a reset token before allowing a password to be chosen."""
    token = serializers.CharField(required=True)

    def validate(self, data):
        token = data.get('token', '').strip()
        if not token:
            raise serializers.ValidationError({'token': 'Reset token is required.'})

        reset_token = PasswordResetToken.objects.filter(token=token).first()
        if not reset_token:
            raise serializers.ValidationError({'token': 'Invalid reset token.'})
        if not reset_token.is_valid():
            raise serializers.ValidationError({'token': 'Reset token has expired or already been used.'})

        data['token'] = token
        data['reset_token'] = reset_token
        return data


class PatientPasswordResetConfirmSerializer(serializers.Serializer):
    """Confirm password reset with token for a patient."""
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        token = data.get('token')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not token or not token.strip():
            raise serializers.ValidationError({'token': 'Reset token is required.'})
        
        if new_password != confirm_password:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        
        try:
            validate_password(new_password)
        except Exception as e:
            raise serializers.ValidationError({'new_password': list(e)})
        
        reset_token = PasswordResetToken.objects.filter(token=token.strip()).first()
        if not reset_token:
            raise serializers.ValidationError({'token': 'Invalid reset token.'})
        
        if not reset_token.is_valid():
            raise serializers.ValidationError({'token': 'Reset token has expired or already been used.'})

        if not reset_token.verified_at:
            raise serializers.ValidationError({'token': 'Reset token must be verified before choosing a new password.'})
        
        data['reset_token'] = reset_token
        return data


class PatientPasswordChangeSerializer(serializers.Serializer):
    """Change password for authenticated patient."""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, data):
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if new_password != confirm_password:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        
        try:
            validate_password(new_password)
        except Exception as e:
            raise serializers.ValidationError({'new_password': list(e)})
        
        patient = self.context['request'].user
        if not hasattr(patient, 'check_password') or not patient.check_password(old_password):
            raise serializers.ValidationError({'old_password': 'Current password is incorrect.'})
        
        if old_password == new_password:
            raise serializers.ValidationError({'new_password': 'New password must be different from current password.'})
        
        return data


class AppointmentScheduleSerializer(serializers.Serializer):
    """Serializer for scheduling appointments."""
    patient_id = serializers.IntegerField()
    doctor_id = serializers.IntegerField(required=False)
    department_id = serializers.IntegerField(required=False, allow_null=True)
    appointment_type = serializers.CharField()
    scheduled_date = serializers.DateField()
    scheduled_time = serializers.TimeField()
    reason = serializers.CharField(required=False)
    notes = serializers.CharField(required=False)
    send_reminder = serializers.BooleanField(required=False, default=False)
    reminder_channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    preferred_channel = serializers.CharField(required=False, allow_blank=True)


class BulkPatientUploadSerializer(serializers.ModelSerializer):
    """Serializer for bulk patient upload records."""
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)

    class Meta:
        model = BulkPatientUpload
        fields = '__all__'
        read_only_fields = [
            'tenant', 'uploaded_by', 'file', 'original_filename',
            'status', 'total_records', 'processed_records',
            'success_count', 'failure_count', 'errors',
            'result_message', 'started_at', 'completed_at'
        ]
