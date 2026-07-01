from django.db import connection
from django.test import TestCase

from .models import Ward
from .serializers import WardSerializer


class WardSerializerTests(TestCase):
    def test_serializer_exposes_staff_count_and_bed_counts(self):
        ward = Ward(
            ward_id='W-001',
            ward_name='Male Ward',
            ward_type='General Ward',
            floor='1',
            supervisor='Nurse Ada',
            staff_count=4,
            total_beds=6,
            notes='Test ward',
        )

        data = WardSerializer(ward).data

        self.assertEqual(data['wardId'], 'W-001')
        self.assertEqual(data['wardName'], 'Male Ward')
        self.assertEqual(data['staffCount'], 4)
        self.assertEqual(data['totalBeds'], 6)

    def test_ward_and_bed_tables_exist_in_database(self):
        tables = connection.introspection.table_names()

        self.assertIn('ward_rounds_ward', tables)
        self.assertIn('ward_rounds_bed', tables)
