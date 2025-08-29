from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from core.models import OutlookCalendar
from core.services.outlook_calendar import MicrosoftGraphService


class Command(BaseCommand):
    help = "List Outlook calendars and test Graph connection"

    def add_arguments(self, parser):
        parser.add_argument('--calendar-id', dest='calendar_id', help='OutlookCalendar UUID to test')

    def handle(self, *args, **options):
        cal_id = options.get('calendar_id')
        qs = OutlookCalendar.objects.all()
        if cal_id:
            qs = qs.filter(id=cal_id)
            if not qs.exists():
                raise CommandError(f"OutlookCalendar {cal_id} not found")

        for oc in qs.select_related('calendar', 'user'):
            svc = MicrosoftGraphService(oc)
            status = svc.test_connection()
            self.stdout.write(self.style.SUCCESS(f"Calendar {oc.id} | {oc.primary_email} | {oc.display_name} | test={status}"))

