from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import LeadFunnel


class Command(BaseCommand):
    help = 'Clean up orphaned LeadFunnels that have no webhook_source or meta_lead_form'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find orphaned funnels (no webhook_source and no meta_lead_form)
        orphaned_funnels = LeadFunnel.objects.filter(
            webhook_source__isnull=True,
            meta_lead_form__isnull=True
        )
        
        count = orphaned_funnels.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('No orphaned funnels found. Database is clean!')
            )
            return
        
        self.stdout.write(f'Found {count} orphaned funnel(s):')
        for funnel in orphaned_funnels:
            self.stdout.write(f'  - {funnel.name} (ID: {funnel.id}, Workspace: {funnel.workspace.workspace_name})')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: No changes made. Use without --dry-run to actually delete.')
            )
            return
        
        # Confirm deletion
        confirm = input(f'Delete {count} orphaned funnel(s)? [y/N]: ')
        if confirm.lower() not in ['y', 'yes']:
            self.stdout.write('Cancelled.')
            return
        
        # Delete orphaned funnels
        with transaction.atomic():
            deleted_count, _ = orphaned_funnels.delete()
            
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {deleted_count} orphaned funnel(s)!')
        )
