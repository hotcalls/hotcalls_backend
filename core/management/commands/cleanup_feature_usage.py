from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import FeatureUsage, WorkspaceUsage, WorkspaceSubscription
from collections import defaultdict


class Command(BaseCommand):
    help = 'Clean up duplicate FeatureUsage records and fix data integrity issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace-id',
            type=str,
            help='Clean up only for specific workspace ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--fix-duplicates',
            action='store_true',
            help='Remove duplicate FeatureUsage records',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        workspace_id = options.get('workspace_id')
        fix_duplicates = options['fix_duplicates']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))

        # Filter workspaces
        queryset = WorkspaceSubscription.objects.filter(is_active=True).select_related('workspace')
        if workspace_id:
            queryset = queryset.filter(workspace__id=workspace_id)

        subscriptions = list(queryset)
        self.stdout.write(f'Checking {len(subscriptions)} active subscription(s)')

        duplicate_count = 0
        fixed_count = 0

        if fix_duplicates:
            # Find and fix duplicate FeatureUsage records
            self.stdout.write('\n🔍 Checking for duplicate FeatureUsage records...')

            # Group by (usage_record, feature) to find duplicates
            usage_groups = defaultdict(list)
            for feature_usage in FeatureUsage.objects.select_related('usage_record', 'feature'):
                key = (feature_usage.usage_record_id, feature_usage.feature_id)
                usage_groups[key].append(feature_usage)

            for key, usages in usage_groups.items():
                if len(usages) > 1:
                    duplicate_count += 1
                    usage_record_id, feature_id = key

                    # Get the usage record and feature for display
                    usage_record = usages[0].usage_record
                    feature = usages[0].feature

                    self.stdout.write(f'  ❌ Found {len(usages)} duplicates for {feature.feature_name} in workspace {usage_record.workspace.workspace_name}')

                    if not dry_run:
                        with transaction.atomic():
                            # Keep the one with the highest used_amount, delete others
                            usages.sort(key=lambda x: x.used_amount, reverse=True)
                            keep = usages[0]
                            delete = usages[1:]

                            for dup in delete:
                                dup.delete()

                            self.stdout.write(f'    ✅ Kept record with used_amount={keep.used_amount}, deleted {len(delete)} duplicates')
                            fixed_count += 1

        # Check for missing FeatureUsage records
        self.stdout.write('\n🔍 Checking for missing FeatureUsage records...')
        missing_count = 0

        for subscription in subscriptions:
            workspace = subscription.workspace
            plan = subscription.plan

            # Get all features in the plan
            plan_features = plan.planfeature_set.all()

            # Get current billing period containers
            workspace_usages = WorkspaceUsage.objects.filter(
                workspace=workspace,
                subscription=subscription
            )

            for usage_container in workspace_usages:
                existing_features = set(
                    usage_container.feature_usages.values_list('feature_id', flat=True)
                )

                for plan_feature in plan_features:
                    if plan_feature.feature_id not in existing_features:
                        missing_count += 1
                        self.stdout.write(f'  ❌ Missing FeatureUsage for {plan_feature.feature.feature_name} in {workspace.workspace_name}')

                        if not dry_run:
                            FeatureUsage.objects.create(
                                usage_record=usage_container,
                                feature=plan_feature.feature,
                                used_amount=0
                            )
                            self.stdout.write(f'    ✅ Created missing FeatureUsage record')
                            fixed_count += 1

        # Summary
        self.stdout.write(f'\n📊 SUMMARY:')
        if fix_duplicates:
            self.stdout.write(f'  🔍 Duplicate groups found: {duplicate_count}')
        self.stdout.write(f'  ❌ Missing records found: {missing_count}')

        if not dry_run:
            self.stdout.write(f'  ✅ Records fixed: {fixed_count}')
            if fixed_count > 0:
                self.stdout.write(self.style.SUCCESS('\n🎉 Cleanup completed!'))
        else:
            total_issues = duplicate_count + missing_count
            self.stdout.write(f'\n🔍 DRY RUN: Would fix {total_issues} issues')
            if total_issues > 0:
                self.stdout.write('Run without --dry-run to apply fixes')