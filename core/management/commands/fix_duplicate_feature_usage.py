from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import FeatureUsage, WorkspaceUsage
from collections import defaultdict
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fix duplicate FeatureUsage records created by double initialization'

    def add_arguments(self, parser):
        parser.add_argument(
            '--workspace-id',
            type=str,
            help='Fix only for specific workspace ID',
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

        # Filter WorkspaceUsage records
        usage_queryset = WorkspaceUsage.objects.all()
        if workspace_id:
            usage_queryset = usage_queryset.filter(workspace__id=workspace_id)

        usage_records = list(usage_queryset.select_related('workspace'))
        self.stdout.write(f'Checking {len(usage_records)} WorkspaceUsage record(s) for duplicate FeatureUsage')

        total_duplicates = 0
        total_fixed = 0

        for usage_record in usage_records:
            workspace_name = usage_record.workspace.workspace_name

            # Group FeatureUsage by feature to find duplicates
            feature_groups = defaultdict(list)
            for feature_usage in usage_record.feature_usages.all():
                feature_groups[feature_usage.feature_id].append(feature_usage)

            # Find groups with duplicates
            duplicate_groups = {k: v for k, v in feature_groups.items() if len(v) > 1}

            if duplicate_groups:
                self.stdout.write(f'\n🔍 Workspace: {workspace_name}')

                for feature_id, duplicates in duplicate_groups.items():
                    feature_name = duplicates[0].feature.feature_name
                    total_duplicates += len(duplicates) - 1

                    self.stdout.write(f'  ❌ Found {len(duplicates)} duplicate FeatureUsage for {feature_name}')

                    if not dry_run:
                        with transaction.atomic():
                            # Keep the one with the highest used_amount, sum others
                            duplicates.sort(key=lambda x: (x.used_amount, x.created_at), reverse=True)
                            keep = duplicates[0]
                            delete_list = duplicates[1:]

                            # Sum the used_amount from all duplicates
                            total_used = sum(dup.used_amount for dup in duplicates)

                            # Update the keeper with total usage
                            keep.used_amount = total_used
                            keep.save(update_fields=['used_amount'])

                            # Delete the duplicates
                            for dup in delete_list:
                                dup.delete()

                            self.stdout.write(f'    ✅ Consolidated {len(duplicates)} records into 1 (total usage: {total_used})')
                            total_fixed += len(delete_list)

        # Summary
        self.stdout.write(f'\n📊 SUMMARY:')
        self.stdout.write(f'  ❌ Duplicate FeatureUsage records found: {total_duplicates}')

        if not dry_run:
            self.stdout.write(f'  ✅ Records consolidated: {total_fixed}')
            if total_fixed > 0:
                self.stdout.write(self.style.SUCCESS('\n🎉 Duplicate cleanup completed!'))
        else:
            self.stdout.write(f'\n🔍 DRY RUN: Would consolidate {total_duplicates} duplicate records')
            if total_duplicates > 0:
                self.stdout.write('Run without --dry-run to apply fixes')