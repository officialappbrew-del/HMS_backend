from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ipd.models import IPDCharge, IPDStay


class Command(BaseCommand):
    help = 'Post daily room and nursing charges for active IPD stays.'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='Charge date in YYYY-MM-DD format')
        parser.add_argument('--room-rate', type=float, default=0)
        parser.add_argument('--nursing-rate', type=float, default=0)

    def handle(self, *args, **options):
        charge_date = timezone.localdate()
        if options.get('date'):
            charge_date = timezone.datetime.strptime(options['date'], '%Y-%m-%d').date()
        created = 0
        for stay in IPDStay.objects.filter(status=IPDStay.Status.ADMITTED).select_related('bed', 'ward'):
            with transaction.atomic():
                if options['room_rate']:
                    _, made = IPDCharge.objects.get_or_create(
                        stay=stay, charge_date=charge_date, category='room', source='nightly_room',
                        description=f'Room rent - {stay.ward.ward_name if stay.ward else "IPD"}',
                        defaults={'quantity': 1, 'unit_price': options['room_rate']},
                    )
                    created += int(made)
                if options['nursing_rate']:
                    _, made = IPDCharge.objects.get_or_create(
                        stay=stay, charge_date=charge_date, category='nursing', source='nightly_nursing',
                        description='Daily nursing charge',
                        defaults={'quantity': 1, 'unit_price': options['nursing_rate']},
                    )
                    created += int(made)
        self.stdout.write(self.style.SUCCESS(f'Created {created} IPD daily charges for {charge_date}.'))
