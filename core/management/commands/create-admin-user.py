from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import User


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--admin-email")
        parser.add_argument("--admin-password")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["admin_email"]
        password = options["admin_password"]
        user = User.objects.create_superuser(email, password)
