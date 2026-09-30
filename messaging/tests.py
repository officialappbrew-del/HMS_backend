from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from patients.models import Patient
from tenants.models import Tenant, TenantUser


class MessagingWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name='Messaging Hospital', domain='messaging-hospital')
        self.other_tenant = Tenant.objects.create(name='Other Hospital', domain='other-messaging-hospital')
        self.patient = Patient.objects.create(
            tenant=self.tenant,
            first_name='Amina',
            last_name='Patient',
            date_of_birth='1992-02-02',
            gender='female',
        )
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(username='triage', email='triage@example.com', password='Password123!')
        self.staff = TenantUser.objects.create(
            tenant=self.tenant,
            global_user=self.staff_user,
            username='triage',
            email='triage@example.com',
            first_name='Triage',
            last_name='Staff',
            phone='08000000000',
            role='receptionist',
        )
        self.other_staff_user = user_model.objects.create_user(username='other', email='other@example.com', password='Password123!')
        self.other_staff = TenantUser.objects.create(
            tenant=self.other_tenant,
            global_user=self.other_staff_user,
            username='other',
            email='other@example.com',
            first_name='Other',
            last_name='Staff',
            phone='08000000001',
            role='nurse',
        )

    def authenticate_patient(self):
        self.patient.is_authenticated = True
        self.patient.is_patient = True
        self.client.force_authenticate(user=self.patient)

    def authenticate_staff(self):
        self.staff_user.tenant_user = self.staff
        self.staff_user.is_tenant_user = True
        self.client.force_authenticate(user=self.staff_user)

    def test_patient_message_is_assigned_and_staff_reply_returns_to_patient(self):
        self.authenticate_patient()
        response = self.client.post('/api/v1/messaging/conversations/', {
            'subject': 'Appointment question',
            'body': 'Can I change my appointment?',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        conversation_id = response.data['id']

        self.authenticate_staff()
        assignment = self.client.post(
            f'/api/v1/messaging/conversations/{conversation_id}/assign/',
            {'assignee_id': self.staff.id},
            format='json',
        )
        self.assertEqual(assignment.status_code, 200)
        reply = self.client.post(
            f'/api/v1/messaging/conversations/{conversation_id}/messages/',
            {'body': 'Your appointment can be changed.'},
            format='json',
        )
        self.assertEqual(reply.status_code, 201)

        self.authenticate_patient()
        messages = self.client.get(f'/api/v1/messaging/conversations/{conversation_id}/messages/')
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(len(messages.data), 2)
        self.assertEqual(messages.data[-1]['body'], 'Your appointment can be changed.')

    def test_patient_cannot_read_internal_staff_note(self):
        self.authenticate_patient()
        created = self.client.post('/api/v1/messaging/conversations/', {'body': 'Please call me.'}, format='json')
        conversation_id = created.data['id']
        self.authenticate_staff()
        self.client.post(f'/api/v1/messaging/conversations/{conversation_id}/assign/', {'assignee_id': self.staff.id}, format='json')
        note = self.client.post(
            f'/api/v1/messaging/conversations/{conversation_id}/messages/',
            {'body': 'Internal triage note.', 'is_internal_note': True},
            format='json',
        )
        self.assertEqual(note.status_code, 201)
        self.authenticate_patient()
        messages = self.client.get(f'/api/v1/messaging/conversations/{conversation_id}/messages/')
        self.assertEqual(len(messages.data), 1)
        self.assertNotIn('Internal triage note.', str(messages.data))

    def test_staff_cannot_assign_a_conversation_to_another_tenant(self):
        self.authenticate_patient()
        created = self.client.post('/api/v1/messaging/conversations/', {'body': 'Need help.'}, format='json')
        self.authenticate_staff()
        response = self.client.post(
            f"/api/v1/messaging/conversations/{created.data['id']}/assign/",
            {'assignee_id': self.other_staff.id},
            format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_staff_chat_is_visible_only_to_participants(self):
        self.authenticate_staff()
        created = self.client.post('/api/v1/messaging/conversations/', {
            'subject': 'Shift handover',
            'body': 'Please review the morning handover.',
            'participant_ids': [self.other_staff.id],
        }, format='json')
        self.assertEqual(created.status_code, 201)
        conversation_id = created.data['id']
        self.other_staff_user.tenant_user = self.other_staff
        self.client.force_authenticate(user=self.other_staff_user)
        detail = self.client.get(f'/api/v1/messaging/conversations/{conversation_id}/')
        self.assertEqual(detail.status_code, 404)