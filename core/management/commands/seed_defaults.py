from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from core.models import Plan, Feature, PlanFeature, Voice, SIPTrunk, PhoneNumber
from core.management.commands.setup_plans import Command as SetupPlansCommand


class Command(BaseCommand):
    help = "Seed default superuser, plans, voice, SIP trunk, and global phone number. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument('--admin-email', default='admin@hotcalls.de')
        parser.add_argument('--admin-password', default='admin')
        parser.add_argument('--voice-id', default='z1EhmmPwF0ENGYE8dBE6', help='External voice id')
        parser.add_argument('--voice-provider', default='elevenlabs')
        parser.add_argument('--voice-name', default='Lukas')
        parser.add_argument('--voice-gender', default='male')
        parser.add_argument('--voice-tone', default='Professionell & Freundlich')
        parser.add_argument('--livekit-trunk-id', default='ST_F5KZ4yNHBegK')
        parser.add_argument('--default-e164', default='+4972195279210')
        # Optional SIP basic placeholders; not secret usage, just non-empty
        parser.add_argument('--sip-provider-name', default='test-provider')
        parser.add_argument('--sip-username', default='testuser')
        parser.add_argument('--sip-password', default='testpass')
        parser.add_argument('--sip-host', default='sip.test.local')
        parser.add_argument('--sip-port', type=int, default=5060)
        parser.add_argument('--force-plans', action='store_true', help='Recreate plans (destructive)')

    @transaction.atomic
    def handle(self, *args, **opts):
        self._ensure_superuser(opts['admin_email'], opts['admin_password'])
        self._ensure_plans(force=opts['force_plans'])
        self._ensure_voice(
            external_id=opts['voice_id'],
            provider=opts['voice_provider'],
            name=opts['voice_name'],
            gender=opts['voice_gender'],
            tone=opts['voice_tone'],
        )
        trunk = self._ensure_sip_trunk(
            provider_name=opts['sip_provider_name'],
            sip_username=opts['sip_username'],
            sip_password=opts['sip_password'],
            sip_host=opts['sip_host'],
            sip_port=opts['sip_port'],
            livekit_trunk_id=opts['livekit_trunk_id'],
        )
        self._ensure_global_phone_number(number=opts['default_e164'], trunk=trunk)
        self.stdout.write(self.style.SUCCESS('✅ Seed complete'))

    def _ensure_superuser(self, email: str, password: str):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
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
            user.set_password(password)
            user.save()
            self.stdout.write(f"👑 Created superuser {email}")
        else:
            # Ensure flags are set
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
            self.stdout.write(f"✔️ Superuser exists: {email}")

    def _ensure_plans(self, force: bool = False):
        self.stdout.write('🪄 Ensuring plans...')
        setup = SetupPlansCommand()
        setup.stdout = self.stdout
        setup.stderr = self.stderr
        setup.handle(force=force)

    def _ensure_voice(self, external_id: str, provider: str, name: str, gender: str, tone: str):
        voice, created = Voice.objects.get_or_create(
            voice_external_id=external_id,
            provider=provider,
            defaults={
                'name': name,
                'gender': gender,
                'tone': tone,
                'recommend': True,
            },
        )
        if not created:
            changed = False
            if voice.name != name:
                voice.name = name; changed = True
            if voice.gender != gender:
                voice.gender = gender; changed = True
            if voice.tone != tone:
                voice.tone = tone; changed = True
            if not voice.recommend:
                voice.recommend = True; changed = True
            if changed:
                voice.save()
        self.stdout.write(f"🎙️ Voice ready: {name} [{provider}:{external_id}]")

    def _ensure_sip_trunk(self, provider_name: str, sip_username: str, sip_password: str, sip_host: str, sip_port: int, livekit_trunk_id: str) -> SIPTrunk:
        trunk, created = SIPTrunk.objects.get_or_create(
            provider_name=provider_name,
            sip_username=sip_username,
            sip_host=sip_host,
            defaults={
                'sip_password': sip_password,
                'sip_port': sip_port,
                'livekit_trunk_id': livekit_trunk_id,
            },
        )
        if not created:
            changed = False
            if trunk.sip_password != sip_password:
                trunk.sip_password = sip_password; changed = True
            if trunk.sip_port != sip_port:
                trunk.sip_port = sip_port; changed = True
            if trunk.livekit_trunk_id != livekit_trunk_id:
                trunk.livekit_trunk_id = livekit_trunk_id; changed = True
            if changed:
                trunk.save()
        self.stdout.write(f"📡 SIP trunk ready: {trunk.provider_name} ({trunk.sip_host}:{trunk.sip_port})")
        return trunk

    def _ensure_global_phone_number(self, number: str, trunk: SIPTrunk):
        phone, created = PhoneNumber.objects.get_or_create(
            phonenumber=number,
            defaults={
                'is_global_default': True,
                'sip_trunk': trunk,
                'is_active': True,
            },
        )
        if not created:
            changed = False
            if not phone.is_global_default:
                phone.is_global_default = True; changed = True
            if phone.sip_trunk_id != trunk.id:
                phone.sip_trunk = trunk; changed = True
            if not phone.is_active:
                phone.is_active = True; changed = True
            if changed:
                phone.save()
        self.stdout.write(f"📞 Global number ready: {phone.phonenumber}")


