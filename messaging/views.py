from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import TenantUser

from .models import Conversation, ConversationParticipant, Message, MessagingNotification
from .serializers import ConversationSerializer, MessageSerializer, MessagingNotificationSerializer


TRIAGE_ROLES = {'admin', 'receptionist', 'doctor', 'nurse'}


def _patient(user):
    return user if getattr(user, 'is_patient', False) else None


def _staff(user):
    if isinstance(user, TenantUser):
        return user
    return getattr(user, 'tenant_user', None)


def _tenant_for(user):
    patient = _patient(user)
    staff = _staff(user)
    return patient.tenant if patient else (staff.tenant if staff else None)


def _notify_staff(conversation, title, text, staff_members, exclude_staff_ids=()):
    recipients = {staff.pk: staff for staff in staff_members if staff and staff.pk not in exclude_staff_ids}
    MessagingNotification.objects.bulk_create([
        MessagingNotification(
            tenant=conversation.tenant,
            conversation=conversation,
            recipient_staff=staff,
            title=title,
            message=text,
        )
        for staff in recipients.values()
    ])


def _notify_patient(conversation, title, text):
    if conversation.patient_id:
        MessagingNotification.objects.create(
            tenant=conversation.tenant,
            conversation=conversation,
            recipient_patient=conversation.patient,
            title=title,
            message=text,
        )


def _conversation_queryset(user):
    patient = _patient(user)
    staff = _staff(user)
    tenant = _tenant_for(user)
    if tenant is None:
        return Conversation.objects.none()
    queryset = Conversation.objects.filter(tenant=tenant).select_related('patient', 'assigned_to')
    if patient:
        return queryset.filter(kind=Conversation.Kind.PATIENT, patient=patient)
    if staff is None:
        return Conversation.objects.none()
    visible = (
        Q(kind=Conversation.Kind.PATIENT, assigned_to=staff)
        | Q(kind=Conversation.Kind.STAFF, participants__tenant_user=staff)
    )
    if staff.role in TRIAGE_ROLES:
        visible |= Q(kind=Conversation.Kind.PATIENT, assigned_to__isnull=True, status__in=[Conversation.Status.OPEN, Conversation.Status.PENDING])
    return queryset.filter(visible).distinct()


def _accessible_conversation(user, conversation_id):
    patient = _patient(user)
    staff = _staff(user)
    tenant = _tenant_for(user)
    if tenant is None:
        raise PermissionDenied('Messaging is available only to a patient or tenant staff account.')
    queryset = Conversation.objects.filter(pk=conversation_id, tenant=tenant)
    if patient:
        queryset = queryset.filter(kind=Conversation.Kind.PATIENT, patient=patient)
    elif staff:
        visible = (
            Q(kind=Conversation.Kind.PATIENT, assigned_to=staff)
            | Q(kind=Conversation.Kind.STAFF, participants__tenant_user=staff)
        )
        if staff.role in TRIAGE_ROLES:
            visible |= Q(kind=Conversation.Kind.PATIENT, assigned_to__isnull=True, status__in=[Conversation.Status.OPEN, Conversation.Status.PENDING])
        queryset = queryset.filter(visible)
    else:
        queryset = queryset.none()
    conversation = get_object_or_404(queryset.distinct(), pk=conversation_id)
    return conversation


def _mark_read(conversation, user):
    now = timezone.now()
    if _patient(user):
        recipient_filter = {'recipient_patient': user}
        participant, _ = ConversationParticipant.objects.get_or_create(conversation=conversation, patient=user)
    else:
        staff = _staff(user)
        recipient_filter = {'recipient_staff': staff}
        participant = None
        if conversation.kind == Conversation.Kind.STAFF:
            participant, _ = ConversationParticipant.objects.get_or_create(conversation=conversation, tenant_user=staff)
    if participant:
        participant.last_read_at = now
        participant.save(update_fields=['last_read_at', 'updated_at'])
    conversation.message_notifications.filter(read_at__isnull=True, **recipient_filter).update(read_at=now, updated_at=now)


class ConversationListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        conversations = _conversation_queryset(request.user)
        kind = request.query_params.get('kind')
        status_filter = request.query_params.get('status')
        if kind in Conversation.Kind.values:
            conversations = conversations.filter(kind=kind)
        if status_filter in Conversation.Status.values:
            conversations = conversations.filter(status=status_filter)
        return Response(ConversationSerializer(conversations[:100], many=True, context={'request': request}).data)

    @transaction.atomic
    def post(self, request):
        patient = _patient(request.user)
        staff = _staff(request.user)
        tenant = _tenant_for(request.user)
        if tenant is None:
            raise PermissionDenied('Messaging is available only to a patient or tenant staff account.')
        subject = str(request.data.get('subject', '')).strip()
        body = str(request.data.get('body', '')).strip()
        subject = subject or ('Message to the hospital' if patient else 'Staff conversation')
        if len(subject) > 180:
            raise ValidationError({'subject': 'Subject must be 180 characters or fewer.'})
        if not body or len(body) > 5000:
            raise ValidationError({'body': 'Enter a message of 1 to 5000 characters.'})

        if patient:
            conversation = Conversation.objects.create(
                tenant=tenant,
                kind=Conversation.Kind.PATIENT,
                patient=patient,
                opened_by_patient=patient,
                subject=subject,
            )
            ConversationParticipant.objects.create(conversation=conversation, patient=patient)
            Message.objects.create(tenant=tenant, conversation=conversation, sender_patient=patient, body=body)
            triage_staff = TenantUser.objects.filter(tenant=tenant, is_active=True, role__in=TRIAGE_ROLES)
            _notify_staff(conversation, 'New patient message', 'A patient conversation needs review.', triage_staff)
        else:
            if not staff or not staff.is_active:
                raise PermissionDenied('An active tenant staff account is required.')
            raw_ids = request.data.get('participant_ids', [])
            if not isinstance(raw_ids, list) or len(raw_ids) > 30:
                raise ValidationError({'participant_ids': 'Provide a list of up to 30 staff IDs.'})
            ids = {staff.pk}
            try:
                ids.update(int(value) for value in raw_ids)
            except (TypeError, ValueError):
                raise ValidationError({'participant_ids': 'Staff IDs must be integers.'})
            if len(ids) < 2:
                raise ValidationError({'participant_ids': 'Select at least one colleague to start a staff chat.'})
            members = list(TenantUser.objects.filter(tenant=tenant, is_active=True, pk__in=ids))
            if len(members) != len(ids):
                raise ValidationError({'participant_ids': 'Every participant must be active staff in your hospital.'})
            conversation = Conversation.objects.create(
                tenant=tenant,
                kind=Conversation.Kind.STAFF,
                opened_by_staff=staff,
                subject=subject,
            )
            ConversationParticipant.objects.bulk_create([
                ConversationParticipant(conversation=conversation, tenant_user=member) for member in members
            ])
            Message.objects.create(tenant=tenant, conversation=conversation, sender_staff=staff, body=body)
            _notify_staff(
                conversation,
                'New staff message',
                'A staff conversation has a new message.',
                members,
                exclude_staff_ids={staff.pk},
            )

        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at', 'updated_at'])
        return Response(ConversationSerializer(conversation, context={'request': request}).data, status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, conversation_id):
        conversation = _accessible_conversation(request.user, conversation_id)
        _mark_read(conversation, request.user)
        return Response(ConversationSerializer(conversation, context={'request': request}).data)


class ConversationMessagesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, conversation_id):
        conversation = _accessible_conversation(request.user, conversation_id)
        _mark_read(conversation, request.user)
        messages = conversation.messages.select_related('sender_staff', 'sender_patient')
        if _patient(request.user):
            messages = messages.filter(is_internal_note=False)
        return Response(MessageSerializer(messages, many=True, context={'request': request}).data)

    @transaction.atomic
    def post(self, request, conversation_id):
        conversation = _accessible_conversation(request.user, conversation_id)
        if conversation.status == Conversation.Status.CLOSED:
            raise ValidationError({'detail': 'This conversation is closed.'})
        body = str(request.data.get('body', '')).strip()
        if not body or len(body) > 5000:
            raise ValidationError({'body': 'Enter a message of 1 to 5000 characters.'})
        internal_note = bool(request.data.get('is_internal_note', False))
        patient = _patient(request.user)
        staff = _staff(request.user)
        if patient and (conversation.kind != Conversation.Kind.PATIENT or internal_note):
            raise PermissionDenied('Patients can only send patient-visible messages in their own conversations.')
        if staff and not staff.is_active:
            raise PermissionDenied('An active tenant staff account is required.')
        message = Message.objects.create(
            tenant=conversation.tenant,
            conversation=conversation,
            sender_patient=patient,
            sender_staff=staff,
            body=body,
            is_internal_note=internal_note,
        )
        now = timezone.now()
        conversation.last_message_at = now
        if patient:
            conversation.status = Conversation.Status.OPEN
            recipients = [conversation.assigned_to] if conversation.assigned_to_id else TenantUser.objects.filter(
                tenant=conversation.tenant, is_active=True, role__in=TRIAGE_ROLES,
            )
            _notify_staff(conversation, 'Patient replied', 'A patient conversation has a new reply.', recipients)
        elif not internal_note:
            if conversation.kind == Conversation.Kind.PATIENT:
                _notify_patient(conversation, 'Hospital replied', 'Your hospital conversation has a new reply.')
            recipients = conversation.participants.filter(tenant_user__is_active=True).exclude(tenant_user=staff).values_list('tenant_user', flat=True)
            _notify_staff(
                conversation,
                'Staff chat reply',
                'A staff conversation has a new reply.',
                TenantUser.objects.filter(pk__in=recipients),
            )
        else:
            recipients = conversation.participants.filter(tenant_user__is_active=True).exclude(tenant_user=staff).values_list('tenant_user', flat=True)
            _notify_staff(
                conversation,
                'Staff note added',
                'A staff-only note was added to a patient conversation.',
                TenantUser.objects.filter(pk__in=recipients),
            )
        conversation.save(update_fields=['last_message_at', 'status', 'updated_at'])
        _mark_read(conversation, request.user)
        return Response(MessageSerializer(message, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AssignConversationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, conversation_id):
        staff = _staff(request.user)
        if not staff or not staff.is_active:
            raise PermissionDenied('Only active hospital staff can assign conversations.')
        conversation = _accessible_conversation(request.user, conversation_id)
        if conversation.kind != Conversation.Kind.PATIENT:
            raise ValidationError({'detail': 'Only patient conversations can be assigned.'})
        assignee_id = request.data.get('assignee_id')
        assignee = None
        if assignee_id not in (None, ''):
            assignee = get_object_or_404(TenantUser, pk=assignee_id, tenant=conversation.tenant, is_active=True)
        conversation.assigned_to = assignee
        conversation.status = Conversation.Status.OPEN if assignee is None else Conversation.Status.PENDING
        conversation.save(update_fields=['assigned_to', 'status', 'updated_at'])
        if conversation.kind == Conversation.Kind.PATIENT:
            conversation.participants.filter(patient__isnull=True).delete()
        if assignee:
            ConversationParticipant.objects.get_or_create(conversation=conversation, tenant_user=assignee)
            MessagingNotification.objects.create(
                tenant=conversation.tenant,
                conversation=conversation,
                recipient_staff=assignee,
                title='Conversation assigned to you',
                message='A patient conversation has been assigned to you.',
            )
        return Response(ConversationSerializer(conversation, context={'request': request}).data)


class ConversationStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, conversation_id):
        staff = _staff(request.user)
        if not staff or not staff.is_active:
            raise PermissionDenied('Only active hospital staff can change conversation status.')
        conversation = _accessible_conversation(request.user, conversation_id)
        new_status = request.data.get('status')
        if new_status not in Conversation.Status.values:
            raise ValidationError({'status': 'Status must be open, pending, or closed.'})
        conversation.status = new_status
        conversation.closed_at = timezone.now() if new_status == Conversation.Status.CLOSED else None
        conversation.save(update_fields=['status', 'closed_at', 'updated_at'])
        if new_status == Conversation.Status.CLOSED:
            _notify_patient(conversation, 'Conversation closed', 'Your hospital conversation has been marked resolved.')
        return Response(ConversationSerializer(conversation, context={'request': request}).data)


class StaffDirectoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        staff = _staff(request.user)
        if not staff:
            raise PermissionDenied('Only hospital staff can view the staff directory for messaging.')
        members = TenantUser.objects.filter(tenant=staff.tenant, is_active=True).select_related('department').order_by('first_name', 'last_name')
        return Response([
            {
                'id': member.pk,
                'name': f'{member.first_name} {member.last_name}'.strip() or member.username or member.email,
                'role': member.get_role_display(),
                'department': member.department.name if member.department_id else '',
            }
            for member in members
        ])


class MessagingNotificationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        patient = _patient(request.user)
        staff = _staff(request.user)
        if patient:
            notifications = MessagingNotification.objects.filter(tenant=patient.tenant, recipient_patient=patient, read_at__isnull=True)
        elif staff:
            notifications = MessagingNotification.objects.filter(tenant=staff.tenant, recipient_staff=staff, read_at__isnull=True)
        else:
            return Response([])
        return Response(MessagingNotificationSerializer(notifications[:50], many=True).data)

    def post(self, request):
        patient = _patient(request.user)
        staff = _staff(request.user)
        if patient:
            notifications = MessagingNotification.objects.filter(tenant=patient.tenant, recipient_patient=patient, read_at__isnull=True)
        elif staff:
            notifications = MessagingNotification.objects.filter(tenant=staff.tenant, recipient_staff=staff, read_at__isnull=True)
        else:
            return Response({'detail': 'No messaging notifications for this account.'})
        notification_id = request.data.get('notification_id')
        if notification_id:
            get_object_or_404(notifications, pk=notification_id).mark_read()
        else:
            notifications.update(read_at=timezone.now(), updated_at=timezone.now())
        return Response({'detail': 'Notification state updated.'})


class MessagingUnreadCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        patient = _patient(request.user)
        staff = _staff(request.user)
        if patient:
            count = MessagingNotification.objects.filter(tenant=patient.tenant, recipient_patient=patient, read_at__isnull=True).count()
        elif staff:
            count = MessagingNotification.objects.filter(tenant=staff.tenant, recipient_staff=staff, read_at__isnull=True).count()
        else:
            count = 0
        return Response({'count': count})