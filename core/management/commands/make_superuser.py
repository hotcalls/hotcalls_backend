from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import User, Workspace, Plan, WorkspaceSubscription
from django.utils import timezone


class Command(BaseCommand):
    help = 'Make a user a superuser by email address'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            type=str,
            help='Email address of the user to make superuser'
        )
        parser.add_argument(
            '--create',
            action='store_true',
            help='Create the user if they do not exist'
        )

    def handle(self, *args, **options):
        email = options['email']
        create_if_not_exists = options['create']

        try:
            with transaction.atomic():
                # Try to get the user
                try:
                    user = User.objects.get(email=email)
                    user_exists = True
                except User.DoesNotExist:
                    if create_if_not_exists:
                        # Create new user
                        user = User.objects.create_user(
                            email=email,
                            password='changeme123!',  # User should change this
                            first_name='Admin',
                            last_name='User',
                            is_email_verified=True
                        )
                        user_exists = False
                        self.stdout.write(
                            self.style.WARNING(f'Created new user {email} with password "changeme123!" - CHANGE THIS PASSWORD!')
                        )
                    else:
                        raise CommandError(f'User with email {email} does not exist. Use --create to create them.')

                # Check if already superuser
                if user.is_superuser:
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ User {email} is already a superuser')
                    )
                    return

                # Make user superuser
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.status = 'active'
                user.is_email_verified = True
                user.save()

                # Setup workspace and Enterprise plan for superuser (if they don't have one)
                if not user.mapping_user_workspaces.exists():
                    workspace = Workspace.objects.create(
                        workspace_name=f"{user.first_name} {user.last_name} Admin Workspace".strip() or f"Admin Workspace ({user.email})"
                    )
                    workspace.users.add(user)
                    self.stdout.write(f'📁 Created workspace: {workspace.workspace_name}')

                    # Get or create Enterprise plan
                    enterprise_plan, created = Plan.objects.get_or_create(
                        plan_name='Enterprise',
                        defaults={
                            'price_monthly': None,  # Custom pricing
                            'is_active': True
                        }
                    )

                    # Create active subscription for the workspace
                    WorkspaceSubscription.objects.create(
                        workspace=workspace,
                        plan=enterprise_plan,
                        started_at=timezone.now(),
                        is_active=True
                    )
                    self.stdout.write(f'🎯 Assigned Enterprise plan to workspace')

                action = 'Updated' if user_exists else 'Created'
                self.stdout.write(
                    self.style.SUCCESS(f'🎉 {action} superuser: {email}')
                )
                self.stdout.write(f'   - is_staff: {user.is_staff}')
                self.stdout.write(f'   - is_superuser: {user.is_superuser}')
                self.stdout.write(f'   - is_active: {user.is_active}')
                self.stdout.write(f'   - status: {user.status}')
                self.stdout.write(f'   - email_verified: {user.is_email_verified}')

        except Exception as e:
            raise CommandError(f'Failed to make user superuser: {str(e)}') 