from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import WorkspaceSubscription
from core.quotas import initialize_feature_usage_for_subscription


class Command(BaseCommand):
    help = 'Initialize FeatureUsage records for all active WorkspaceSubscriptions (eager initialization backfill)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace-id',
            type=str,
            help='Initialize only for specific workspace ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        workspace_id = options.get('workspace_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))

        # Filter subscriptions
        queryset = WorkspaceSubscription.objects.filter(is_active=True).select_related('plan', 'workspace')

        if workspace_id:
            queryset = queryset.filter(workspace__id=workspace_id)

        subscriptions = list(queryset)

        if not subscriptions:
            self.stdout.write(self.style.WARNING('No active subscriptions found'))
            return

        self.stdout.write(f'Found {len(subscriptions)} active subscription(s) to process')

        success_count = 0
        error_count = 0

        for subscription in subscriptions:
            workspace_name = subscription.workspace.workspace_name
            plan_name = subscription.plan.plan_name

            try:
                if dry_run:
                    self.stdout.write(f'  🔍 Would initialize: {workspace_name} ({plan_name})')
                else:
                    with transaction.atomic():
                        usage_container = initialize_feature_usage_for_subscription(subscription)
                        feature_count = usage_container.feature_usages.count()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✅ Initialized {feature_count} features for: {workspace_name} ({plan_name})'
                            )
                        )
                success_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Failed to initialize {workspace_name} ({plan_name}): {str(e)}')
                )
                error_count += 1

        # Summary
        if dry_run:
            self.stdout.write(f'\n🔍 DRY RUN SUMMARY: Would process {success_count} subscriptions')
        else:
            self.stdout.write(f'\n📊 SUMMARY:')
            self.stdout.write(f'  ✅ Success: {success_count}')
            if error_count > 0:
                self.stdout.write(f'  ❌ Errors: {error_count}')
            self.stdout.write(f'  📈 Total processed: {success_count + error_count}')

        if success_count > 0 and not dry_run:
            self.stdout.write(self.style.SUCCESS('\n🎉 FeatureUsage initialization completed!'))