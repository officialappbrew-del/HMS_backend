import uuid

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from lab.models import LabResult
from patients.models import Patient
from .models import IntegrationClient, IntegrationMessage
from .services import FHIRService, HL7Service


class IntegrationAPIKeyAuthentication(permissions.BasePermission):
    """Allow safe partner and device authentication using a pre-shared API key."""

    message = 'Valid integration API key required.'

    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False

        token = auth_header.split(' ', 1)[1].strip()
        if not token:
            return False

        # Match the token strictly against registered clients by their prefix.
        # No arbitrary fallback client is used to avoid authentication bypass.
        for candidate in IntegrationClient.objects.filter(is_active=True):
            if candidate.api_key_prefix and token.startswith(candidate.api_key_prefix):
                if candidate.verify_api_key(token):
                    request.integration_client = candidate
                    return True

        return False


class FHIRIntegrationViewSet(ViewSet):
    """Minimal FHIR interoperability endpoints for external systems."""
    permission_classes = [IntegrationAPIKeyAuthentication]

    def list(self, request):
        tenant = getattr(getattr(request, 'integration_client', None), 'tenant', None)
        patients = Patient.objects.filter(tenant=tenant) if tenant else Patient.objects.none()
        payload = {
            'resourceType': 'Bundle',
            'type': 'searchset',
            'entry': [
                {'resource': FHIRService.patient_to_fhir(patient)} for patient in patients[:50]
            ],
        }
        IntegrationMessage.objects.create(
            source_system='partner',
            direction=IntegrationMessage.Direction.OUTBOUND,
            message_type='patient-search',
            protocol='fhir',
            status=IntegrationMessage.Status.ACCEPTED,
            resource_type='Bundle',
            correlation_id=str(uuid.uuid4()),
            payload=payload,
            tenant=tenant,
            client=getattr(request, 'integration_client', None),
        )
        return Response(payload)

    def retrieve(self, request, pk=None):
        tenant = getattr(getattr(request, 'integration_client', None), 'tenant', None)
        patient = get_object_or_404(Patient, pk=pk, tenant=tenant) if tenant else get_object_or_404(Patient, pk=pk)
        payload = FHIRService.patient_to_fhir(patient)
        IntegrationMessage.objects.create(
            source_system='partner',
            direction=IntegrationMessage.Direction.OUTBOUND,
            message_type='patient-read',
            protocol='fhir',
            resource_type='Patient',
            status=IntegrationMessage.Status.ACCEPTED,
            correlation_id=str(uuid.uuid4()),
            payload=payload,
            tenant=tenant or patient.tenant,
            client=getattr(request, 'integration_client', None),
        )
        return Response(payload)

    def create(self, request):
        resource = request.data
        resource_type = resource.get('resourceType')

        if resource_type == 'Patient':
            identifier = resource.get('identifier', [{}])[0]
            patient_id = identifier.get('value') or resource.get('id')
            if patient_id:
                try:
                    patient = Patient.objects.get(hospital_number=patient_id)
                    payload = FHIRService.patient_to_fhir(patient)
                    IntegrationMessage.objects.create(
                        source_system='partner',
                        direction=IntegrationMessage.Direction.INBOUND,
                        message_type='patient-create',
                        protocol='fhir',
                        resource_type='Patient',
                        status=IntegrationMessage.Status.ACCEPTED,
                        correlation_id=str(uuid.uuid4()),
                        payload=resource,
                        raw_payload=str(resource),
                        tenant=patient.tenant,
                        client=getattr(request, 'integration_client', None),
                    )
                    return Response(payload, status=status.HTTP_200_OK)
                except Patient.DoesNotExist:
                    return Response({'detail': 'Patient not found in HMS.'}, status=status.HTTP_404_NOT_FOUND)

            return Response({'detail': 'Patient identifier is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if resource_type == 'Observation':
            subject_ref = resource.get('subject', {}).get('reference', '')
            patient_id = subject_ref.replace('Patient/', '') if subject_ref.startswith('Patient/') else None
            if patient_id is None:
                return Response({'detail': 'Observation subject patient reference is required.'}, status=status.HTTP_400_BAD_REQUEST)

            result = LabResult.objects.filter(order__patient_id=patient_id).order_by('-created_at').first()
            if not result:
                return Response({'detail': 'No lab result found for this patient.'}, status=status.HTTP_404_NOT_FOUND)

            return Response(FHIRService.lab_result_to_observation(result))

        return Response({'detail': f'Unsupported resource type: {resource_type}'}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def capability_statement(request):
        return Response({
            'resourceType': 'CapabilityStatement',
            'status': 'active',
            'name': 'SmartCare HMS Interoperability',
            'kind': 'instance',
            'fhirVersion': '4.0.1',
            'format': ['application/fhir+json'],
            'rest': [{
                'mode': 'server',
                'resource': [
                    {'type': 'Patient', 'interaction': [{'code': 'read'}, {'code': 'search-type'}]},
                    {'type': 'Observation', 'interaction': [{'code': 'read'}, {'code': 'create'}]},
                ],
            }],
        })


class IntegrationClientCreateAPIView(APIView):
    """Create a new external integration client with a generated API key."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        description = request.data.get('description', '')
        prefix = request.data.get('prefix', 'hms_')
        tenant = getattr(request.user, 'tenant_user', None)
        tenant = tenant.tenant if tenant else None

        if not name:
            return Response({'detail': 'Client name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if IntegrationClient.objects.filter(name=name).exists():
            return Response({'detail': 'Client name already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        client, raw_key = IntegrationClient.generate_api_key(name=name, tenant=tenant, description=description, prefix=prefix)
        return Response({
            'id': client.id,
            'name': client.name,
            'tenant_id': tenant.id if tenant else None,
            'api_key_prefix': client.api_key_prefix,
            'api_key': raw_key,
            'authorization_header': f'Bearer {raw_key}',
        }, status=status.HTTP_201_CREATED)


class IntegrationMessageListAPIView(APIView):
    """List all interoperability messages for audit and operations review."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queryset = IntegrationMessage.objects.all()
        if getattr(request.user, 'tenant_user', None):
            queryset = queryset.filter(tenant=request.user.tenant_user.tenant)
        message_type = request.query_params.get('message_type')
        protocol = request.query_params.get('protocol')
        if message_type:
            queryset = queryset.filter(message_type=message_type)
        if protocol:
            queryset = queryset.filter(protocol=protocol)
        return Response([
            {
                'id': message.id,
                'source_system': message.source_system,
                'destination_system': message.destination_system,
                'direction': message.direction,
                'message_type': message.message_type,
                'protocol': message.protocol,
                'resource_type': message.resource_type,
                'status': message.status,
                'correlation_id': message.correlation_id,
                'tenant_id': message.tenant_id,
                'created_at': message.created_at.isoformat() if message.created_at else None,
                'payload': message.payload,
            }
            for message in queryset.order_by('-created_at')[:100]
        ])


class HL7IntegrationAPIView(APIView):
    """Accept raw HL7 v2 messages from lab instruments, PACS, and external hospitals."""
    permission_classes = [IntegrationAPIKeyAuthentication]

    def post(self, request, *args, **kwargs):
        raw_message = request.data.get('message') if isinstance(request.data, dict) else request.data
        if not isinstance(raw_message, str):
            return Response({'detail': 'A raw HL7 message string is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parsed = HL7Service.parse_message(raw_message)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # HL7 messages come from authenticated integration clients (API key),
        # NOT from request.user (which is AnonymousUser for API-key auth).
        # Use request.integration_client.tenant to scope the ingest correctly.
        tenant = getattr(request, 'integration_client', None)
        tenant = tenant.tenant if tenant else None

        try:
            ingestion_result = HL7Service.create_lab_result_from_hl7(raw_message, tenant=tenant)
        except Exception:
            ingestion_result = {'accepted': False, 'reason': 'Could not ingest HL7 message into HMS.'}

        if not ingestion_result.get('accepted', False):
            ack = HL7Service.build_ack(raw_message, success=False, message=ingestion_result.get('reason', 'Message rejected'))
            return Response({
                'accepted': False,
                'parsed': parsed,
                'ack': ack,
                'reason': ingestion_result.get('reason', 'Message rejected'),
            }, status=status.HTTP_400_BAD_REQUEST)

        ack = HL7Service.build_ack(raw_message, success=True, message='Message accepted and stored')
        IntegrationMessage.objects.create(
            source_system='external-lab',
            direction=IntegrationMessage.Direction.INBOUND,
            message_type=parsed.get('message_type', 'hl7-message'),
            protocol='hl7',
            status=IntegrationMessage.Status.ACCEPTED,
            correlation_id=str(uuid.uuid4()),
            payload={
                'parsed': parsed,
                'ingestion': ingestion_result,
            },
            raw_payload=raw_message,
            tenant=tenant,
            client=getattr(request, 'integration_client', None),
        )
        return Response({
            'accepted': True,
            'parsed': parsed,
            'ingestion': ingestion_result,
            'ack': ack,
        }, status=status.HTTP_202_ACCEPTED)
