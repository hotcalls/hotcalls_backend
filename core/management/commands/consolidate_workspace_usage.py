from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import WorkspaceUsage, FeatureUsage, WorkspaceSubscription
from collections import defaultdict
from decimal import Decimal


class Command(BaseCommand):
    help = 'Consolidate duplicate WorkspaceUsage records and fix subscription tracking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace-id',
            type=str,
            help='Consolidate only for specific workspace ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--fix-duplicates',
            action='store_true',
            help='Consolidate duplicate WorkspaceUsage records',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        workspace_id = options.get('workspace_id')
        fix_duplicates = options['fix_duplicates']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))

        # Get all WorkspaceUsage records
        queryset = WorkspaceUsage.objects.select_related('workspace', 'subscription')
        if workspace_id:
            queryset = queryset.filter(workspace__id=workspace_id)

        usage_records = list(queryset)
        self.stdout.write(f'Analyzing {len(usage_records)} WorkspaceUsage record(s)')

        if fix_duplicates:
            # Group by (workspace, period_start, period_end) to find duplicates
            self.stdout.write('\n🔍 Checking for duplicate WorkspaceUsage records...')

            usage_groups = defaultdict(list)
            for usage in usage_records:
                key = (usage.workspace_id, usage.period_start, usage.period_end)
                usage_groups[key].append(usage)

            duplicate_groups = {k: v for k, v in usage_groups.items() if len(v) > 1}
            consolidated_count = 0

            for key, duplicates in duplicate_groups.items():
                workspace_id, period_start, period_end = key
                workspace = duplicates[0].workspace

                self.stdout.write(f'  ❌ Found {len(duplicates)} WorkspaceUsage records for {workspace.workspace_name} ({period_start} → {period_end})')

                if not dry_run:
                    with transaction.atomic():
                        # Find the most recent subscription (active one preferred)
                        active_subscription = None
                        latest_subscription = None

                        for usage in duplicates:
                            if usage.subscription.is_active:
                                active_subscription = usage.subscription
                            if latest_subscription is None or usage.subscription.created_at > latest_subscription.created_at:
                                latest_subscription = usage.subscription

                        # Use active subscription if available, otherwise latest
                        target_subscription = active_subscription or latest_subscription

                        # Create/get the consolidated container
                        consolidated_usage, created = WorkspaceUsage.objects.get_or_create(
                            workspace=workspace,
                            period_start=period_start,
                            period_end=period_end,
                            defaults={
                                'subscription': target_subscription,
                                'extra_call_minutes': Decimal('0')
                            }
                        )

                        if not created:
                            # Update to point to target subscription
                            consolidated_usage.subscription = target_subscription
                            consolidated_usage.save(update_fields=['subscription'])

                        # Consolidate FeatureUsage records from all duplicates
                        feature_usage_totals = defaultdict(Decimal)

                        for usage in duplicates:
                            if usage.id == consolidated_usage.id:
                                continue  # Skip the target container

                            # Sum up all FeatureUsage amounts
                            for feature_usage in usage.feature_usages.all():
                                feature_usage_totals[feature_usage.feature_id] += feature_usage.used_amount

                            # Add extra call minutes
                            if usage.extra_call_minutes:
                                consolidated_usage.extra_call_minutes += usage.extra_call_minutes

                            # Delete the duplicate container (cascades to FeatureUsage)
                            usage.delete()

                        # Update consolidated FeatureUsage records with totals
                        for feature_id, total_amount in feature_usage_totals.items():
                            feature_usage, created = FeatureUsage.objects.get_or_create(
                                usage_record=consolidated_usage,
                                feature_id=feature_id,
                                defaults={'used_amount': total_amount}
                            )
                            if not created:
                                feature_usage.used_amount += total_amount
                                feature_usage.save(update_fields=['used_amount'])

                        # Save extra minutes if updated
                        if consolidated_usage.extra_call_minutes > 0:
                            consolidated_usage.save(update_fields=['extra_call_minutes'])

                        self.stdout.write(f'    ✅ Consolidated into 1 record pointing to {target_subscription.plan.plan_name} subscription')
                        consolidated_count += 1

        # Check for WorkspaceUsage pointing to inactive subscriptions
        self.stdout.write('\n🔍 Checking for WorkspaceUsage pointing to inactive subscriptions...')
        inactive_usage_count = 0
        updated_count = 0

        for usage in usage_records:
            if not usage.subscription.is_active:
                inactive_usage_count += 1
                workspace = usage.workspace

                # Find active subscription for this workspace
                try:
                    active_subscription = WorkspaceSubscription.objects.get(
                        workspace=workspace,
                        is_active=True
                    )

                    self.stdout.write(f'  ⚠️ WorkspaceUsage for {workspace.workspace_name} points to inactive {usage.subscription.plan.plan_name} subscription')

                    if not dry_run:
                        usage.subscription = active_subscription
                        usage.save(update_fields=['subscription'])
                        self.stdout.write(f'    ✅ Updated to point to active {active_subscription.plan.plan_name} subscription')
                        updated_count += 1

                except WorkspaceSubscription.DoesNotExist:
                    self.stdout.write(f'  ❌ No active subscription found for {workspace.workspace_name}')

        # Summary
        self.stdout.write(f'\n📊 SUMMARY:')
        if fix_duplicates:
            self.stdout.write(f'  🔍 Duplicate groups found: {len(duplicate_groups)}')
            if not dry_run:
                self.stdout.write(f'  ✅ Groups consolidated: {consolidated_count}')

        self.stdout.write(f'  ⚠️ Usage pointing to inactive subscriptions: {inactive_usage_count}')
        if not dry_run:
            self.stdout.write(f'  ✅ Records updated: {updated_count}')

        if not dry_run and (consolidated_count > 0 or updated_count > 0):
            self.stdout.write(self.style.SUCCESS('\n🎉 WorkspaceUsage consolidation completed!'))