from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Patient, PatientMerge


def _tenant_user(user):
    tenant_user = getattr(user, 'tenant_user', None)
    if tenant_user is not None:
        return tenant_user
    if getattr(getattr(user, '_meta', None), 'label_lower', None) == 'tenants.tenantuser':
        return user
    return None


def merge_patients(source_id, survivor_id, tenant, user, reason):
    """Move all patient foreign-key rows and retain enough data to reverse it."""
    if source_id == survivor_id:
        raise ValidationError({'survivor_id': 'A patient cannot be merged into itself.'})
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A clinical or administrative reason is required.'})

    with transaction.atomic():
        source = Patient.objects.select_for_update().get(pk=source_id, tenant=tenant)
        survivor = Patient.objects.select_for_update().get(pk=survivor_id, tenant=tenant)
        if source.merged_into_id:
            raise ValidationError({'source_patient': 'This patient has already been merged.'})
        if survivor.merged_into_id:
            raise ValidationError({'survivor_id': 'The survivor is itself a merged record.'})

        moved_records = []
        for model in apps.get_models():
            if model in (Patient, PatientMerge) or not model._meta.managed:
                continue
            patient_field = next(
                (field for field in model._meta.get_fields()
                 if getattr(field, 'many_to_one', False)
                 and getattr(field, 'related_model', None) is Patient
                 and field.name == 'patient'),
                None,
            )
            if patient_field is None:
                continue
            queryset = model.objects.filter(patient_id=source.pk)
            if any(field.name == 'tenant' for field in model._meta.fields):
                queryset = queryset.filter(tenant_id=tenant.pk)
            for record in queryset.iterator():
                try:
                    record.patient_id = survivor.pk
                    record.save(update_fields=['patient'])
                except IntegrityError:
                    # Preserve conflicting source rows; they remain reversible and visible.
                    transaction.set_rollback(False)
                    continue
                moved_records.append({
                    'model': model._meta.label_lower,
                    'id': str(record.pk),
                })

        source.merged_into = survivor
        source.merged_at = timezone.now()
        source.merged_by = _tenant_user(user)
        source.merge_reason = reason.strip()
        source.patient_status = 'inactive'
        source.is_active = False
        source.save(update_fields=[
            'merged_into', 'merged_at', 'merged_by', 'merge_reason',
            'patient_status', 'is_active', 'updated_at',
        ])
        merge_record = PatientMerge.objects.create(
            tenant=tenant,
            source_patient=source,
            survivor_patient=survivor,
            merged_by=_tenant_user(user),
            reason=reason.strip(),
            moved_records=moved_records,
        )
    return merge_record


def unmerge_patient(merge_record, user):
    """Reverse only rows that still point at the recorded survivor."""
    with transaction.atomic():
        merge_record = PatientMerge.objects.select_for_update().select_related(
            'source_patient', 'survivor_patient'
        ).get(pk=merge_record.pk)
        if merge_record.status != 'active':
            raise ValidationError({'merge': 'This merge has already been unmerged.'})

        source = Patient.objects.select_for_update().get(pk=merge_record.source_patient_id)
        restored_records = []
        for item in merge_record.moved_records:
            model = apps.get_model(item['model'])
            record = model.objects.filter(pk=item['id'], patient_id=merge_record.survivor_patient_id).first()
            if record is None:
                continue
            record.patient_id = source.pk
            try:
                record.save(update_fields=['patient'])
            except IntegrityError:
                transaction.set_rollback(False)
                continue
            restored_records.append(item)

        source.merged_into = None
        source.merged_at = None
        source.merged_by = None
        source.merge_reason = ''
        source.patient_status = 'active'
        source.is_active = True
        source.save(update_fields=[
            'merged_into', 'merged_at', 'merged_by', 'merge_reason',
            'patient_status', 'is_active', 'updated_at',
        ])
        merge_record.status = 'unmerged'
        merge_record.unmerged_at = timezone.now()
        merge_record.unmerged_by = _tenant_user(user)
        merge_record.moved_records = [
            item for item in merge_record.moved_records if item not in restored_records
        ]
        merge_record.save(update_fields=['status', 'unmerged_at', 'unmerged_by', 'moved_records', 'updated_at'])
    return merge_record