from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Voice

class Command(BaseCommand):

    @transaction.atomic
    def handle(self, *args, **options):
        voices = [
            {
                'external_id': 'z1EhmmPwF0ENGYE8dBE6',
                'provider': 'elevenlabs',
                'name': 'Lukas',
                'gender': 'male',
                'tone': 'Professionell & Freundlich',
                'recommend': True,
             },
            {
                'external_id': 'L0yTtpRXzdyzQlzALhgD',
                'provider': 'elevenlabs',
                'name': 'Lisa',
                'gender': 'female',
                'tone': 'Jung & Energetisch',
                'recommend': False,
             },
            {
                'external_id': 'nF7t9cuYo0u3kuVI9q4B',
                'provider': 'elevenlabs',
                'name': 'Anna',
                'gender': 'female',
                'tone': 'Ruhig & Sachlich',
                'recommend': False,
             },
        ]

        for voice in voices:
            voice_obj, created = Voice.objects.get_or_create(
                voice_external_id=voice['external_id'],
                provider=voice['provider'],
                defaults={
                    'name': voice['name'],
                    'gender': voice['gender'],
                    'tone': voice['tone'],
                    'recommend': voice['recommend'],
                },
            )

            if not created:
                changed = False
                if voice_obj.name != voice['name']:
                    voice_obj.name = voice['name']
                    changed = True
                if voice_obj.gender != voice['gender']:
                    voice_obj.gender = voice['gender']
                    changed = True
                if voice_obj.tone != voice['tone']:
                    voice_obj.tone = voice['tone']
                    changed = True
                if changed:
                    voice_obj.save()
