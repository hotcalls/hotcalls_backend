from django.core.management.base import BaseCommand
from core.models import User, Workspace, Agent, WorkspaceSubscription, WorkspaceUsage, FeatureUsage


class Command(BaseCommand):
    help = 'Nuclear deletion of Martin Bischof user account and ALL related data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            default='mail@bischofmartin.com',
            help='Email address of user to delete (default: mail@bischofmartin.com)'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the deletion (required for safety)'
        )

    def handle(self, *args, **options):
        email = options['email']
        confirm = options['confirm']
        
        if not confirm:
            self.stdout.write(
                self.style.ERROR('❌ DELETION ABORTED: Use --confirm flag to proceed')
            )
            self.stdout.write('Example: python manage.py delete_martin --confirm')
            return

        self.stdout.write(self.style.WARNING(f'💥 NUCLEAR DELETION: {email}'))
        self.stdout.write(self.style.WARNING('⚠️  THIS WILL DELETE EVERYTHING!'))
        
        try:
            # Find the user
            user = User.objects.get(email=email)
            self.stdout.write(f'Found user: {user.first_name} {user.last_name} ({user.email})')
            self.stdout.write(f'User ID: {user.id}')
            
            # Find all workspaces the user owns or is a member of
            user_workspaces = Workspace.objects.filter(users=user)
            self.stdout.write(f'\nFound {user_workspaces.count()} workspaces:')
            
            for workspace in user_workspaces:
                self.stdout.write(f'  - {workspace.workspace_name} (ID: {workspace.id})')
                
                # Step 1: Delete all agents in workspace
                agents = Agent.objects.filter(workspace=workspace)
                agent_count = agents.count()
                agents.delete()
                self.stdout.write(f'    ✅ Deleted {agent_count} agents')
                
                # Step 2: Get WorkspaceUsage records for this workspace
                workspace_usage_records = WorkspaceUsage.objects.filter(workspace=workspace)
                usage_count = workspace_usage_records.count()
                
                # Step 3: Delete FeatureUsage records first (correct relationship)
                feature_usage_total = 0
                for usage_record in workspace_usage_records:
                    feature_usage = FeatureUsage.objects.filter(usage_record=usage_record)
                    feature_count = feature_usage.count()
                    feature_usage_total += feature_count
                    feature_usage.delete()
                self.stdout.write(f'    ✅ Deleted {feature_usage_total} feature usage records')
                
                # Step 4: Delete WorkspaceUsage records
                workspace_usage_records.delete()
                self.stdout.write(f'    ✅ Deleted {usage_count} workspace usage records')
                
                # Step 5: Delete WorkspaceSubscription records
                subscriptions = WorkspaceSubscription.objects.filter(workspace=workspace)
                sub_count = subscriptions.count()
                subscriptions.delete()
                self.stdout.write(f'    ✅ Deleted {sub_count} subscription records')
                
                # Step 6: Clear any direct plan references
                if hasattr(workspace, 'current_plan') and workspace.current_plan:
                    workspace.current_plan = None
                    workspace.save()
                    self.stdout.write('    ✅ Cleared workspace plan reference')
                
                # Step 7: Delete the workspace
                workspace_name = workspace.workspace_name
                workspace.delete()
                self.stdout.write(f'    ✅ Deleted workspace: {workspace_name}')
            
            # Final step: Delete the user
            user_email = user.email
            user_name = f'{user.first_name} {user.last_name}'
            user.delete()
            self.stdout.write(self.style.SUCCESS(f'\n🗑️ DELETED USER: {user_name} ({user_email})'))
            
            self.stdout.write(self.style.SUCCESS('\n💥 NUCLEAR DELETION COMPLETE!'))
            self.stdout.write('- User account completely removed')
            self.stdout.write('- All workspaces removed')
            self.stdout.write('- All agents removed')
            self.stdout.write('- All subscription records removed')
            self.stdout.write('- All usage tracking removed')
            self.stdout.write(f'- Everything related to {email} is GONE!')
            
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ User with email {email} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error during deletion: {e}'))
            import traceback
            self.stdout.write(traceback.format_exc())