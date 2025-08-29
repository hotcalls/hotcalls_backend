from django.core.management.base import BaseCommand, CommandError
from core.models import OutlookCalendar, OutlookSubAccount
from core.services.outlook_calendar import OutlookCalendarService


class Command(BaseCommand):
    help = "Discover Outlook sub-accounts (delegated/shared) for a given OutlookCalendar and list results"

    def add_arguments(self, parser):
        parser.add_argument('calendar_id', help='OutlookCalendar UUID')

    def handle(self, *args, **options):
        cal_id = options['calendar_id']
        try:
            oc = OutlookCalendar.objects.get(id=cal_id)
        except OutlookCalendar.DoesNotExist:
            raise CommandError(f"OutlookCalendar {cal_id} not found")

        svc = OutlookCalendarService()
        created = svc.discover_and_update_sub_accounts(oc)
        self.stdout.write(self.style.SUCCESS(f"Discovery created {len(created)} sub-accounts: {created}"))

        sub_accounts = OutlookSubAccount.objects.filter(outlook_calendar=oc).order_by('relationship', 'act_as_upn')
        for sa in sub_accounts:
            self.stdout.write(f"- {sa.act_as_upn} | rel={sa.relationship} | active={sa.active}")

