import uuid

from django.shortcuts import get_object_or_404
from django.db import models
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from lab.models import LabResult
from patients.models import Patient
from .models import IntegrationClient, IntegrationMessage, MirthChannel
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
                    allowed_ips = candidate.allowed_ip_addresses or []
                    if allowed_ips and request.META.get('REMOTE_ADDR') not in allowed_ips:
                        continue
                    candidate.last_used = timezone.now()
                    candidate.save(update_fields=['last_used', 'updated_at'])
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

    def get(self, request, *args, **kwargs):
        if not _staff_user(request):
            return Response({'detail': 'Administrator permission required.'}, status=status.HTTP_403_FORBIDDEN)
        tenant = getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        clients = IntegrationClient.objects.filter(tenant=tenant, is_active=True).order_by('name')
        return Response([{
            'id': client.id,
            'name': client.name,
            'description': client.description,
            'api_key_prefix': client.api_key_prefix,
        } for client in clients])

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


def _staff_user(request):
    user = request.user
    role = getattr(getattr(user, 'tenant_user', None), 'role', None) or getattr(user, 'role', None)
    return bool(getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False) or role in {'admin', 'tenant_admin', 'super_admin', 'system_admin'})


class MirthChannelListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _staff_user(request):
            return Response({'detail': 'Administrator permission required.'}, status=status.HTTP_403_FORBIDDEN)
        tenant = getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        channels = MirthChannel.objects.filter(tenant=tenant).select_related('client')
        return Response([self._serialize(channel, request) for channel in channels])

    def post(self, request):
        if not _staff_user(request):
            return Response({'detail': 'Administrator permission required.'}, status=status.HTTP_403_FORBIDDEN)
        tenant = getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        if tenant is None:
            return Response({'detail': 'Tenant context required.'}, status=status.HTTP_400_BAD_REQUEST)
        required = ['name', 'source_system', 'client_id']
        missing = [field for field in required if not request.data.get(field)]
        if missing:
            return Response({field: 'This field is required.' for field in missing}, status=status.HTTP_400_BAD_REQUEST)
        client = get_object_or_404(IntegrationClient, pk=request.data['client_id'], tenant=tenant, is_active=True)
        channel = MirthChannel.objects.create(
            tenant=tenant, client=client, name=request.data['name'].strip(),
            source_system=request.data['source_system'].strip(), protocol=request.data.get('protocol', 'hl7'),
            direction=request.data.get('direction', 'inbound'), mirth_base_url=request.data.get('mirth_base_url', '').strip(),
            channel_id=request.data.get('channel_id', '').strip(), settings=request.data.get('settings') or {},
        )
        return Response(self._serialize(channel, request), status=status.HTTP_201_CREATED)

    @staticmethod
    def _serialize(channel, request):
        return {
            'id': channel.id, 'name': channel.name, 'source_system': channel.source_system,
            'protocol': channel.protocol, 'direction': channel.direction, 'status': channel.status,
            'mirth_base_url': channel.mirth_base_url, 'channel_id': channel.channel_id,
            'client_id': channel.client_id, 'client_name': channel.client.name,
            'inbound_url': request.build_absolute_uri('/api/v1/integration/mirth/inbound/'),
            'last_health_check': channel.last_health_check, 'last_message_at': channel.last_message_at,
            'error_count': channel.error_count,
        }


class MirthChannelHealthAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _staff_user(request):
            return Response({'detail': 'Administrator permission required.'}, status=status.HTTP_403_FORBIDDEN)
        tenant = getattr(getattr(request.user, 'tenant_user', None), 'tenant', None)
        channel = get_object_or_404(MirthChannel, pk=pk, tenant=tenant)
        channel.last_health_check = timezone.now()
        channel.save(update_fields=['last_health_check', 'updated_at'])
        return Response({'healthy': True, 'detail': 'HMS inbound endpoint is available.', 'channel_id': channel.id})


class MirthInboundAPIView(APIView):
    """Receive one FHIR Observation transformed by a Mirth Connect channel."""
    permission_classes = [IntegrationAPIKeyAuthentication]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else None
        if not payload or payload.get('resourceType') != 'Observation':
            return Response({'accepted': False, 'detail': 'Send one normalized FHIR Observation from Mirth Connect.'}, status=status.HTTP_400_BAD_REQUEST)
        client = request.integration_client
        tenant = client.tenant
        correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())
        existing = IntegrationMessage.objects.filter(client=client, correlation_id=correlation_id).first()
        if existing:
            return Response({'accepted': existing.status == IntegrationMessage.Status.ACCEPTED, 'duplicate': True, 'correlation_id': correlation_id})
        message = IntegrationMessage.objects.create(
            source_system=client.name, destination_system='smartcare-hms', direction=IntegrationMessage.Direction.INBOUND,
            message_type='lab-result', protocol='fhir', resource_type='Observation', status=IntegrationMessage.Status.QUEUED,
            correlation_id=correlation_id, payload=payload, raw_payload=request.body.decode('utf-8', errors='replace'),
            ip_address=request.META.get('REMOTE_ADDR'), tenant=tenant, client=client,
        )
        try:
            ingestion = FHIRService.ingest_observation(payload, tenant=tenant)
            message.status = IntegrationMessage.Status.ACCEPTED
            message.payload = {**payload, 'ingestion': ingestion}
            message.save(update_fields=['status', 'payload', 'updated_at'])
            MirthChannel.objects.filter(client=client, tenant=tenant).update(last_message_at=timezone.now())
            return Response({'accepted': True, 'correlation_id': correlation_id, 'ingestion': ingestion}, status=status.HTTP_202_ACCEPTED)
        except Exception as exc:
            message.status = IntegrationMessage.Status.REJECTED
            message.payload = {'error': str(exc), 'resource': payload}
            message.save(update_fields=['status', 'payload', 'updated_at'])
            MirthChannel.objects.filter(client=client, tenant=tenant).update(error_count=models.F('error_count') + 1)
            return Response({'accepted': False, 'correlation_id': correlation_id, 'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


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
