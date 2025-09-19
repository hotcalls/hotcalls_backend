from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import WorkspaceSubscription, Workspace
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up duplicate WorkspaceSubscription records per workspace'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without making changes',
        )
        parser.add_argument(
            '--fix-active',
            action='store_true',
            help='Fix workspaces with multiple active subscriptions',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix_active = options['fix_active']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Find workspaces with multiple active subscriptions
        workspaces_with_duplicates = []

        for workspace in Workspace.objects.all():
            active_subscriptions = WorkspaceSubscription.objects.filter(
                workspace=workspace,
                is_active=True
            ).order_by('-created_at')  # Most recent first

            if active_subscriptions.count() > 1:
                workspaces_with_duplicates.append({
                    'workspace': workspace,
                    'active_count': active_subscriptions.count(),
                    'subscriptions': list(active_subscriptions)
                })

        self.stdout.write(
            f"Found {len(workspaces_with_duplicates)} workspaces with multiple active subscriptions"
        )

        if not workspaces_with_duplicates:
            self.stdout.write(self.style.SUCCESS("No duplicate active subscriptions found!"))
            return

        # Show details
        for item in workspaces_with_duplicates:
            workspace = item['workspace']
            subscriptions = item['subscriptions']

            self.stdout.write(f"\nWorkspace: {workspace.workspace_name} ({workspace.id})")
            self.stdout.write(f"  Active subscriptions: {item['active_count']}")

            for i, sub in enumerate(subscriptions):
                self.stdout.write(
                    f"    {i+1}. Plan: {sub.plan.plan_name}, Created: {sub.created_at}, "
                    f"Started: {sub.started_at}"
                )

        if not fix_active:
            self.stdout.write(
                self.style.WARNING(
                    "\nTo fix these duplicates, run again with --fix-active"
                )
            )
            return

        if not dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nProceeding to fix duplicates..."
                )
            )

        # Fix duplicates
        fixed_count = 0
        for item in workspaces_with_duplicates:
            workspace = item['workspace']
            subscriptions = item['subscriptions']

            # Keep the most recent one, deactivate others
            keep_subscription = subscriptions[0]  # Most recent (ordered by -created_at)
            deactivate_subscriptions = subscriptions[1:]

            self.stdout.write(
                f"\nFixing workspace {workspace.workspace_name}:"
            )
            self.stdout.write(
                f"  Keeping: {keep_subscription.plan.plan_name} "
                f"(created {keep_subscription.created_at})"
            )

            for sub in deactivate_subscriptions:
                self.stdout.write(
                    f"  Deactivating: {sub.plan.plan_name} "
                    f"(created {sub.created_at})"
                )

                if not dry_run:
                    with transaction.atomic():
                        sub.is_active = False
                        sub.save()

            fixed_count += 1

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDRY RUN: Would fix {fixed_count} workspaces"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nFixed {fixed_count} workspaces with duplicate subscriptions"
                )
            )

        # Verify no more duplicates
        remaining_duplicates = 0
        for workspace in Workspace.objects.all():
            active_count = WorkspaceSubscription.objects.filter(
                workspace=workspace,
                is_active=True
            ).count()
            if active_count > 1:
                remaining_duplicates += 1

        if remaining_duplicates == 0:
            self.stdout.write(
                self.style.SUCCESS("✅ All duplicate subscriptions have been resolved!")
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ {remaining_duplicates} workspaces still have multiple active subscriptions"
                )
            )