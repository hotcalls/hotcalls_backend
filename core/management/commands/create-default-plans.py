from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import User

class Command(BaseCommand):

    @transaction.atomic
    def handle(self, *args, **options):
        return
