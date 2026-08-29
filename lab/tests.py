from django.test import TestCase
from django.utils import timezone

from lab.serializers import InstrumentMaintenanceSerializer


class InstrumentMaintenanceSerializerTimezoneTests(TestCase):
    def test_scheduled_date_is_made_timezone_aware(self):
        serializer = InstrumentMaintenanceSerializer(
            data={
                'instrument_name': 'Chemistry Analyzer',
                'instrument_type': 'Analyzer',
                'maintenance_type': 'routine',
                'description': 'Routine servicing',
                'status': 'pending',
                'priority': 'high',
                'scheduled_date': '2026-09-05T00:00:00',
                'performed_by': 'Technician',
                'cost': '250.00',
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNotNone(serializer.validated_data['scheduled_date'])
        self.assertFalse(timezone.is_naive(serializer.validated_data['scheduled_date']))
