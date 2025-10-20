from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import User

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--admin-email")
        parser.add_argument("--admin-password")

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            email=options["admin-email"],
            defaults={
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
                'is_email_verified': True,
                'status': 'active',
            },
        )
        if created:
            user.set_password(options["admin-password"])
            user.save()
        else:
            updated = False
            for attr, val in {
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
                'is_email_verified': True,
                'status': 'active',
            }.items():
                if getattr(user, attr, None) != val:
                    setattr(user, attr, val)
                    updated = True
            if updated:
                user.save()
