from datetime import datetime
from typing import Any, Dict, List, Optional

from django.utils import timezone
from django.db import transaction

from lab.models import LabResult, LabOrder, LabTest
from patients.models import Patient


class FHIRService:
    """Convert internal HMS records into FHIR-compatible resources."""

    @staticmethod
    def patient_to_fhir(patient: Patient) -> Dict[str, Any]:
        return {
            'resourceType': 'Patient',
            'id': str(patient.id),
            'identifier': [
                {'system': 'https://smartcarehms.com/patient/hospital-number', 'value': patient.hospital_number},
                {'system': 'https://smartcarehms.com/patient/mrn', 'value': patient.mrn or ''},
            ],
            'active': bool(getattr(patient, 'is_active', True)),
            'name': [{
                'family': patient.last_name,
                'given': [name for name in [patient.first_name, patient.middle_name] if name],
            }],
            'gender': (patient.gender or 'unknown').lower() if patient.gender else 'unknown',
            'birthDate': patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            'telecom': [
                {'system': 'phone', 'value': patient.phone} if patient.phone else None,
                {'system': 'email', 'value': patient.email} if patient.email else None,
            ],
            'address': [{
                'line': [patient.address] if patient.address else [],
                'city': patient.city,
                'state': patient.state,
                'country': patient.country,
            }] if patient.address or patient.city or patient.state or patient.country else [],
            'extension': [
                {'url': 'https://smartcarehms.com/patient/tenant-code', 'valueString': str(getattr(patient.tenant, 'code', ''))},
            ] if getattr(patient, 'tenant', None) else [],
        }

    @staticmethod
    def lab_result_to_observation(result: LabResult) -> Dict[str, Any]:
        return {
            'resourceType': 'Observation',
            'id': str(result.id),
            'status': 'final',
            'code': {
                'coding': [{
                    'system': 'https://smartcarehms.com/lab/tests',
                    'code': getattr(result.order.test, 'code', ''),
                    'display': getattr(result.order.test, 'name', 'Lab Test'),
                }],
                'text': getattr(result.order.test, 'name', 'Lab Test'),
            },
            'subject': {'reference': f'Patient/{result.order.patient_id}'},
            'effectiveDateTime': result.created_at.isoformat(),
            'valueString': result.value,
            'interpretation': [{'text': result.flag or 'Normal'}] if result.flag else [],
            'referenceRange': [{
                'text': result.reference_range or ''
            }] if result.reference_range else [],
            'issued': result.created_at.isoformat(),
        }

    @staticmethod
    @transaction.atomic
    def ingest_observation(resource: Dict[str, Any], tenant=None) -> Dict[str, Any]:
        """Persist a FHIR Observation already normalized by Mirth Connect."""
        if resource.get('resourceType') != 'Observation':
            raise ValueError('Mirth inbound payload must contain a FHIR Observation.')

        subject = resource.get('subject') or {}
        reference = str(subject.get('reference') or '')
        patient_identifier = reference.split('/', 1)[1] if reference.startswith('Patient/') else ''
        patient = HL7Service.find_patient_by_hl7_identifier(patient_identifier, tenant=tenant)
        if patient is None:
            raise ValueError('Observation patient was not found in this tenant.')

        coding = (resource.get('code') or {}).get('coding') or [{}]
        code = coding[0].get('code') or 'MIRTH-UNKNOWN'
        name = coding[0].get('display') or (resource.get('code') or {}).get('text') or code
        value = resource.get('valueQuantity') or {}
        value_text = value.get('value', resource.get('valueString', ''))
        lab_test, _ = LabTest.objects.get_or_create(
            tenant=patient.tenant, code=code,
            defaults={'name': name, 'category': 'other', 'sample_type': 'blood', 'turnaround_time': 24},
        )
        order = LabOrder.objects.filter(
            tenant=patient.tenant, patient=patient, test=lab_test,
        ).order_by('-ordered_date').first()
        if order is None:
            order = LabOrder.objects.create(
                tenant=patient.tenant, patient=patient, test=lab_test,
                order_number=f"MIRTH-{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
                status='completed',
            )
        result = LabResult.objects.create(
            tenant=patient.tenant, order=order, value=str(value_text),
            value_numeric=float(value_text) if HL7Service._is_numeric(value_text) else None,
            units=value.get('unit', ''),
            reference_range=(resource.get('referenceRange') or [{}])[0].get('text', ''),
            is_critical=any('critical' in str(item).lower() for item in (resource.get('interpretation') or [])),
            flag=(resource.get('interpretation') or [{}])[0].get('coding', [{}])[0].get('code', ''),
            result_notes='Imported from Mirth Connect normalized FHIR',
            is_verified=True,
        )
        return {'patient_id': patient.id, 'order_id': order.id, 'result_id': result.id, 'test_code': code}


class HL7Service:
    """Convert a small subset of HL7 v2 messages to internal payloads."""

    @staticmethod
    def parse_message(raw_message: str) -> Dict[str, Any]:
        if not raw_message or not raw_message.strip():
            raise ValueError('HL7 message is empty.')

        lines = [line.strip() for line in raw_message.splitlines() if line.strip()]
        if not lines:
            raise ValueError('No HL7 segments found.')

        msh = lines[0].split('|')
        message_type = msh[8] if len(msh) > 8 else ''
        event_type = msh[9] if len(msh) > 9 else ''

        patient = {}
        observation = {}
        observations: List[Dict[str, Any]] = []

        for line in lines[1:]:
            seg = line.split('|')
            if seg[0] == 'PID':
                patient = {
                    'patient_id': seg[3] if len(seg) > 3 else '',
                    'last_name': seg[5].split('^')[0] if len(seg) > 5 else '',
                    'first_name': seg[5].split('^')[1] if len(seg) > 5 and '^' in seg[5] else '',
                    'dob': seg[7] if len(seg) > 7 else '',
                    'sex': seg[8] if len(seg) > 8 else '',
                }
            elif seg[0] == 'OBX':
                observation = {
                    'test_code': seg[3].split('^')[0] if len(seg) > 3 else '',
                    'test_name': seg[3].split('^')[1] if len(seg) > 3 and '^' in seg[3] else '',
                    'value': seg[5] if len(seg) > 5 else '',
                    'units': seg[6] if len(seg) > 6 else '',
                    'status': seg[11] if len(seg) > 11 else '',
                    'reference_range': seg[7] if len(seg) > 7 else '',
                    'flag': seg[8] if len(seg) > 8 else '',
                }
                observations.append(observation)

        return {
            'message_type': message_type,
            'event_type': event_type,
            'patient': patient,
            'observations': observations,
            'raw_segments': len(lines),
            'source': 'hl7-v2',
        }

    @staticmethod
    def find_patient_by_hl7_identifier(patient_id: str, tenant=None) -> Optional[Patient]:
        if not patient_id:
            return None
        qs = Patient.objects.all()
        if tenant is not None:
            qs = qs.filter(tenant=tenant)
        return (
            qs.filter(hospital_number=patient_id).first()
            or qs.filter(mrn=patient_id).first()
            or qs.filter(login_id=patient_id).first()
            or qs.filter(nin=patient_id).first()
        )

    @staticmethod
    def create_lab_result_from_hl7(raw_message: str, tenant=None) -> Dict[str, Any]:
        parsed = HL7Service.parse_message(raw_message)
        patient_payload = parsed.get('patient') or {}
        patient_id = patient_payload.get('patient_id') or patient_payload.get('identifier')
        patient = HL7Service.find_patient_by_hl7_identifier(str(patient_id), tenant=tenant)

        if patient is None:
            return {
                'accepted': False,
                'reason': 'Patient not found',
                'parsed': parsed,
            }

        observations = parsed.get('observations') or []
        if not observations:
            return {
                'accepted': False,
                'reason': 'No OBX observations found',
                'parsed': parsed,
            }

        first_observation = observations[0]
        test_code = first_observation.get('test_code') or 'HL7-UNKNOWN'
        test_name = first_observation.get('test_name') or test_code
        numeric_value = first_observation.get('value') or ''

        lab_test, _ = LabTest.objects.get_or_create(
            tenant=tenant or patient.tenant,
            code=test_code,
            defaults={
                'name': test_name,
                'category': 'other',
                'sample_type': 'blood',
                'turnaround_time': 24,
                'reference_range': first_observation.get('reference_range') or '',
                'units': first_observation.get('units') or '',
            },
        )

        order, _ = LabOrder.objects.get_or_create(
            tenant=tenant or patient.tenant,
            patient=patient,
            test=lab_test,
            defaults={
                'order_number': f"HL7-{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
                'status': 'completed',
            },
        )
        if not order.order_number:
            order.order_number = f"HL7-{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
            order.save(update_fields=['order_number'])

        result = LabResult.objects.create(
            tenant=tenant or patient.tenant,
            order=order,
            value=str(numeric_value),
            value_numeric=float(numeric_value) if self._is_numeric(numeric_value) else None,
            units=first_observation.get('units') or '',
            reference_range=first_observation.get('reference_range') or '',
            is_critical=bool(first_observation.get('flag') in {'HH', 'LL'}),
            flag=first_observation.get('flag') or '',
            result_notes='Imported from HL7 v2 message',
            is_verified=True,
        )

        return {
            'accepted': True,
            'patient_id': patient.id,
            'patient_hospital_number': patient.hospital_number,
            'order_id': order.id,
            'result_id': result.id,
            'test_code': test_code,
            'parsed': parsed,
        }

    @staticmethod
    def _is_numeric(value):
        try:
            float(str(value).strip())
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def build_ack(raw_message: str, success: bool = True, message: str = 'OK') -> str:
        now = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        ack_code = 'AA' if success else 'AR'
        msh = raw_message.splitlines()[0].split('|') if raw_message.splitlines() else []
        sending_app = msh[2] if len(msh) > 2 else 'SMARTCARE'
        sending_facility = msh[3] if len(msh) > 3 else 'HMS'
        receiving_app = msh[5] if len(msh) > 5 else 'HMS'
        receiving_facility = msh[6] if len(msh) > 6 else 'SMARTCARE'

        return (
            f'MSH|^~\\&|{receiving_app}|{receiving_facility}|{sending_app}|{sending_facility}|{now}||ACK|{hash(raw_message) % 100000}|P|2.5\r'
            f'MSA|{ack_code}|{message}\r'
        )
