"""
Google Calendar Health Check Management Command

Usage:
    python manage.py google_calendar_health
    python manage.py google_calendar_health --refresh-tokens
    python manage.py google_calendar_health --verbose
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
from core.models import GoogleCalendar
from core.services.google_calendar import GoogleCalendarService
import logging


class Command(BaseCommand):
    help = 'Check and manage Google Calendar token health'

    def add_arguments(self, parser):
        parser.add_argument(
            '--refresh-tokens',
            action='store_true',
            help='Attempt to refresh all expiring tokens',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed information for each calendar',
        )
        parser.add_argument(
            '--force-refresh',
            action='store_true',
            help='Force refresh all tokens regardless of expiry',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up expired tokens older than 7 days',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 Google Calendar Health Check')
        )
        self.stdout.write('=' * 50)

        # Get current status
        now = timezone.now()
        all_calendars = GoogleCalendar.objects.all()
        
        stats = {
            'total': all_calendars.count(),
            'healthy': 0,
            'expiring_soon': 0,
            'expired': 0,
            'missing_tokens': 0,
            'details': []
        }

        for calendar in all_calendars:
            status = self.check_calendar_health(calendar, now)
            stats[status['category']] += 1
            stats['details'].append(status)
            
            if options['verbose']:
                self.print_calendar_details(status)

        # Print summary
        self.print_summary(stats)

        # Handle options
        if options['refresh_tokens'] or options['force_refresh']:
            self.refresh_tokens(all_calendars, force=options['force_refresh'])
        
        if options['cleanup']:
            self.cleanup_expired_tokens()

    def check_calendar_health(self, calendar, now):
        """Check the health status of a single calendar"""
        status = {
            'name': calendar.calendar.name,
            'external_id': calendar.external_id,
            'category': 'healthy',
            'issue': None,
            'expires_at': calendar.token_expires_at,
            'calendar': calendar
        }

        # Check for missing tokens
        if not calendar.access_token or not calendar.refresh_token:
            status['category'] = 'missing_tokens'
            status['issue'] = 'Missing access or refresh token'
            return status

        # Check expiry
        if not calendar.token_expires_at:
            status['category'] = 'missing_tokens'
            status['issue'] = 'No expiry time set'
            return status

        if calendar.token_expires_at < now:
            time_expired = now - calendar.token_expires_at
            status['category'] = 'expired'
            status['issue'] = f'Expired {time_expired} ago'
        elif calendar.token_expires_at < now + timedelta(hours=24):
            time_until_expiry = calendar.token_expires_at - now
            status['category'] = 'expiring_soon'
            status['issue'] = f'Expires in {time_until_expiry}'

        return status

    def print_calendar_details(self, status):
        """Print detailed information for a calendar"""
        category_colors = {
            'healthy': self.style.SUCCESS,
            'expiring_soon': self.style.WARNING,
            'expired': self.style.ERROR,
            'missing_tokens': self.style.ERROR
        }
        
        color = category_colors.get(status['category'], self.style.SUCCESS)
        
        self.stdout.write(
            f"📅 {status['name']}"
        )
        self.stdout.write(
            f"   Status: {color(status['category'].replace('_', ' ').title())}"
        )
        if status['issue']:
            self.stdout.write(f"   Issue: {status['issue']}")
        if status['expires_at']:
            self.stdout.write(f"   Expires: {status['expires_at']}")
        self.stdout.write("")

    def print_summary(self, stats):
        """Print summary statistics"""
        self.stdout.write("\n📊 SUMMARY:")
        self.stdout.write(f"📅 Total calendars: {stats['total']}")
        self.stdout.write(
            self.style.SUCCESS(f"✅ Healthy: {stats['healthy']}")
        )
        self.stdout.write(
            self.style.WARNING(f"⚠️  Expiring soon: {stats['expiring_soon']}")
        )
        self.stdout.write(
            self.style.ERROR(f"❌ Expired: {stats['expired']}")
        )
        self.stdout.write(
            self.style.ERROR(f"🚫 Missing tokens: {stats['missing_tokens']}")
        )

        if stats['expired'] > 0 or stats['missing_tokens'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  {stats['expired'] + stats['missing_tokens']} calendars need attention!"
                )
            )
            self.stdout.write("Run with --refresh-tokens to attempt fixes")

    def refresh_tokens(self, calendars, force=False):
        """Attempt to refresh tokens"""
        self.stdout.write(
            self.style.WARNING('\n🔄 Refreshing tokens...')
        )
        
        now = timezone.now()
        refresh_threshold = now + timedelta(hours=24) if not force else now + timedelta(days=365)
        
        calendars_to_refresh = calendars.filter(
            token_expires_at__lt=refresh_threshold,
            refresh_token__isnull=False
        ).exclude(refresh_token='')
        
        success_count = 0
        failure_count = 0
        
        for calendar in calendars_to_refresh:
            try:
                service = GoogleCalendarService(calendar)
                credentials = service.get_credentials()
                
                if credentials:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ Refreshed: {calendar.calendar.name}")
                    )
                else:
                    failure_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"❌ Failed: {calendar.calendar.name}")
                    )
                    
            except Exception as e:
                failure_count += 1
                self.stdout.write(
                    self.style.ERROR(f"❌ Error for {calendar.calendar.name}: {str(e)}")
                )
        
        self.stdout.write(
            f"\n📊 Refresh Results: {success_count} success, {failure_count} failures"
        )

    def cleanup_expired_tokens(self):
        """Clean up tokens expired for more than 7 days"""
        self.stdout.write(
            self.style.WARNING('\n🧹 Cleaning up expired tokens...')
        )
        
        now = timezone.now()
        cleanup_threshold = now - timedelta(days=7)
        
        expired_calendars = GoogleCalendar.objects.filter(
            token_expires_at__lt=cleanup_threshold
        ).exclude(
            access_token__isnull=True,
            refresh_token__isnull=True
        )
        
        cleaned_count = 0
        
        for calendar in expired_calendars:
            calendar.access_token = None
            calendar.refresh_token = None
            calendar.save(update_fields=['access_token', 'refresh_token', 'updated_at'])
            
            cleaned_count += 1
            self.stdout.write(
                f"🧹 Cleaned: {calendar.calendar.name}"
            )
        
        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Cleaned {cleaned_count} calendars")
        ) 