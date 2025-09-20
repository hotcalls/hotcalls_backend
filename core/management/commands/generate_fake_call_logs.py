import random
import uuid
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import (
    Workspace, Agent, Lead, CallLog, DisconnectionReason,
    PhoneNumber, SIPTrunk, Voice
)


class Command(BaseCommand):
    help = """
🎭 PRODUCTION FAKE DATA GENERATOR - Generate realistic call logs for dashboard demo

Creates a full year of realistic business data:
- 📊 Leads with German names and realistic contact info
- 📞 Call logs with proper reach rates and appointment conversion
- 📅 Appointment scheduling with realistic timing
- 🧪 Test calls sprinkled throughout
- 📈 Realistic monthly variation (±30%)

DEFAULT SETTINGS (Realistic Business Metrics):
- 150 leads/month per workspace (1,800/year)
- 35% reach rate (leads that get contacted successfully)
- 25% appointment rate (of reached leads)
- 20 test calls/month per workspace

PRODUCTION USAGE:
python manage.py generate_fake_call_logs

CUSTOM SETTINGS:
python manage.py generate_fake_call_logs --leads-per-month 200 --reached-rate 0.4 --appointment-rate 0.3

⚠️ SAFETY: Use --clear-existing to replace all data (requires confirmation)
"""

    def add_arguments(self, parser):
        parser.add_argument(
            '--leads-per-month',
            type=int,
            default=150,
            help='Average number of new leads per workspace per month (varies ±30%)'
        )
        parser.add_argument(
            '--reached-rate',
            type=float,
            default=0.35,
            help='Percentage of leads that get reached (0.0-1.0)'
        )
        parser.add_argument(
            '--appointment-rate',
            type=float,
            default=0.25,
            help='Percentage of reached leads that result in appointments (0.0-1.0)'
        )
        parser.add_argument(
            '--test-calls-per-month',
            type=int,
            default=20,
            help='Average number of test calls per workspace per month'
        )
        parser.add_argument(
            '--full-year',
            action='store_true',
            default=True,
            help='Generate full year of data (365 days)'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='⚠️ DANGER: Clear ALL existing call logs and leads before generating'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🎭 PRODUCTION FAKE DATA GENERATOR STARTING..."))

        leads_per_month = options['leads_per_month']
        reached_rate = options['reached_rate']
        appointment_rate = options['appointment_rate']
        test_calls_per_month = options['test_calls_per_month']
        clear_existing = options['clear_existing']

        # Production safety check
        if clear_existing:
            self.stdout.write(self.style.WARNING("⚠️⚠️⚠️ DANGER: About to clear ALL existing data!"))
            confirm = input("Type 'YES DELETE ALL DATA' to confirm: ")
            if confirm != "YES DELETE ALL DATA":
                self.stdout.write("❌ Operation cancelled")
                return

            self.stdout.write("🗑️ Clearing existing call logs and leads...")
            CallLog.objects.all().delete()
            Lead.objects.all().delete()
            self.stdout.write("✅ Existing data cleared")

        workspaces = Workspace.objects.all()
        if not workspaces.exists():
            self.stdout.write(self.style.ERROR("❌ No workspaces found. Run 'python manage.py seed_defaults' first."))
            return

        # Global statistics tracking
        global_stats = {
            'total_leads': 0,
            'total_calls': 0,
            'total_reached': 0,
            'total_appointments': 0,
            'total_test_calls': 0,
            'workspace_details': {}
        }

        self.stdout.write(f"📊 Will generate data for {workspaces.count()} workspaces across full year")
        self.stdout.write(f"📈 Target rates: {reached_rate*100:.1f}% reached, {appointment_rate*100:.1f}% appointments from reached")

        for workspace in workspaces:
            self.stdout.write(f"\n📋 Processing workspace: {workspace.workspace_name}")

            # Get or create an agent for this workspace
            agent = self._ensure_agent_for_workspace(workspace)
            if not agent:
                self.stdout.write(f"⚠️ Skipping workspace {workspace.workspace_name} - no agent")
                continue

            workspace_stats = self._generate_year_data(
                workspace, agent, leads_per_month, reached_rate,
                appointment_rate, test_calls_per_month
            )

            # Track global stats
            global_stats['total_leads'] += workspace_stats['leads_created']
            global_stats['total_calls'] += workspace_stats['total_calls']
            global_stats['total_reached'] += workspace_stats['reached_calls']
            global_stats['total_appointments'] += workspace_stats['appointment_calls']
            global_stats['total_test_calls'] += workspace_stats['test_calls']
            global_stats['workspace_details'][workspace.workspace_name] = workspace_stats

            # Print workspace summary
            self.stdout.write(f"  ✅ {workspace.workspace_name} Summary:")
            self.stdout.write(f"     💼 Leads: {workspace_stats['leads_created']}")
            self.stdout.write(f"     📞 Total Calls: {workspace_stats['total_calls']}")
            self.stdout.write(f"     ✅ Reached: {workspace_stats['reached_calls']} ({workspace_stats['reached_calls']/workspace_stats['total_calls']*100:.1f}%)")
            self.stdout.write(f"     📅 Appointments: {workspace_stats['appointment_calls']} ({workspace_stats['appointment_calls']/workspace_stats['reached_calls']*100:.1f}% of reached)")
            self.stdout.write(f"     🧪 Test Calls: {workspace_stats['test_calls']}")

        # Print global summary
        self.stdout.write(self.style.SUCCESS("\n🎉 PRODUCTION DATA GENERATION COMPLETE!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("📊 GLOBAL SUMMARY:"))
        self.stdout.write(self.style.SUCCESS(f"💼 Total Leads Created: {global_stats['total_leads']:,}"))
        self.stdout.write(self.style.SUCCESS(f"📞 Total Calls Made: {global_stats['total_calls']:,}"))
        self.stdout.write(self.style.SUCCESS(f"✅ Total Reached: {global_stats['total_reached']:,} ({global_stats['total_reached']/global_stats['total_calls']*100:.1f}%)"))
        self.stdout.write(self.style.SUCCESS(f"📅 Total Appointments: {global_stats['total_appointments']:,} ({global_stats['total_appointments']/global_stats['total_reached']*100:.1f}% of reached)"))
        self.stdout.write(self.style.SUCCESS(f"🧪 Total Test Calls: {global_stats['total_test_calls']:,}"))
        self.stdout.write(self.style.SUCCESS(f"🏢 Workspaces Processed: {workspaces.count()}"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

    def _generate_year_data(self, workspace, agent, leads_per_month, reached_rate, appointment_rate, test_calls_per_month):
        """Generate a full year of realistic call data for a workspace"""
        stats = {
            'leads_created': 0,
            'total_calls': 0,
            'reached_calls': 0,
            'appointment_calls': 0,
            'test_calls': 0
        }

        # Generate data month by month for more realistic distribution
        now = timezone.now()
        for month_offset in range(12):
            # Calculate month start/end
            month_start = now - timedelta(days=365 - (month_offset * 30))
            month_end = month_start + timedelta(days=30)

            # Vary monthly volume ±30%
            month_leads = int(leads_per_month * random.uniform(0.7, 1.3))
            month_test_calls = int(test_calls_per_month * random.uniform(0.7, 1.3))

            # Generate leads for this month
            month_leads_objs = self._generate_monthly_leads(workspace, month_leads, month_start, month_end)
            stats['leads_created'] += len(month_leads_objs)

            # Generate calls for these leads
            month_stats = self._generate_monthly_calls(
                workspace, agent, month_leads_objs, reached_rate,
                appointment_rate, month_start, month_end
            )

            # Generate test calls
            test_stats = self._generate_monthly_test_calls(
                workspace, agent, month_test_calls, month_start, month_end
            )

            # Update stats
            stats['total_calls'] += month_stats['total_calls'] + test_stats['test_calls']
            stats['reached_calls'] += month_stats['reached_calls']
            stats['appointment_calls'] += month_stats['appointment_calls']
            stats['test_calls'] += test_stats['test_calls']

        return stats

    def _ensure_agent_for_workspace(self, workspace):
        """Get or create an agent for the workspace"""
        agent = workspace.mapping_workspace_agents.first()
        if agent:
            return agent

        # Create a basic agent if none exists
        voice = Voice.objects.first()
        phone = PhoneNumber.objects.filter(is_active=True).first()

        if not phone:
            # Create a basic phone number if none exists
            sip_trunk = self._ensure_sip_trunk()
            phone = PhoneNumber.objects.create(
                phonenumber=f"+49{random.randint(1000000000, 9999999999)}",
                sip_trunk=sip_trunk,
                is_active=True
            )

        agent = Agent.objects.create(
            workspace=workspace,
            name=f"Test Agent {workspace.workspace_name}",
            status='active',
            voice=voice,
            phone_number=phone
        )
        return agent

    def _ensure_sip_trunk(self):
        """Get or create a SIP trunk"""
        trunk = SIPTrunk.objects.first()
        if trunk:
            return trunk

        return SIPTrunk.objects.create(
            provider_name="Test Provider",
            sip_username="testuser",
            sip_password="testpass",
            sip_host="sip.test.local",
            sip_port=5060,
            is_active=True
        )

    def _generate_monthly_leads(self, workspace, count, month_start, month_end):
        """Generate fake leads for a specific month"""
        leads = []

        # German names for realistic data
        first_names = [
            "Max", "Anna", "Thomas", "Julia", "Michael", "Lisa", "Andreas", "Sarah",
            "Stefan", "Nicole", "Daniel", "Christina", "Martin", "Petra", "Christian",
            "Sabine", "Frank", "Andrea", "Markus", "Claudia", "Tobias", "Susanne",
            "Alexander", "Monika", "Patrick", "Birgit", "Matthias", "Katrin", "Sven",
            "Sandra", "Oliver", "Marion", "Sebastian", "Anja", "Jörg", "Karin",
            "Heinrich", "Gisela", "Ralf", "Ingrid", "Uwe", "Brigitte", "Klaus", "Renate"
        ]

        last_names = [
            "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
            "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
            "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun",
            "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Schmitz",
            "Krause", "Meier", "Lehmann", "Schmid", "Schulze", "Maier", "Köhler",
            "Herrmann", "König", "Walter", "Peters", "Kaiser", "Jung", "Friedrich"
        ]

        domains = ["gmail.com", "web.de", "gmx.de", "outlook.com", "yahoo.de", "t-online.de", "hotmail.de"]

        for i in range(count):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)

            # Spread lead creation times throughout the month
            lead_created = month_start + timedelta(
                days=random.randint(0, (month_end - month_start).days),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )

            lead = Lead.objects.create(
                workspace=workspace,
                name=first_name,
                surname=last_name,
                email=f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 9999)}@{random.choice(domains)}",
                phone=f"+49{random.randint(1500000000, 1799999999)}",  # German mobile numbers
                integration_provider='manual',
                created_at=lead_created
            )
            leads.append(lead)

        return leads

    def _generate_monthly_calls(self, workspace, agent, leads, reached_rate, appointment_rate, month_start, month_end):
        """Generate calls for leads with realistic reach and appointment rates"""
        stats = {
            'total_calls': 0,
            'reached_calls': 0,
            'appointment_calls': 0
        }

        # Determine which leads get reached and which get appointments
        reached_leads = random.sample(leads, int(len(leads) * reached_rate))
        appointment_leads = random.sample(reached_leads, int(len(reached_leads) * appointment_rate))

        for lead in leads:
            # Each lead gets 1-3 call attempts (more attempts for unreached)
            is_reached = lead in reached_leads
            is_appointment = lead in appointment_leads

            if is_reached:
                num_calls = random.choices([1, 2], weights=[70, 30])[0]  # Reached leads need fewer calls
            else:
                num_calls = random.choices([1, 2, 3], weights=[30, 40, 30])[0]  # Unreached leads get more attempts

            for attempt in range(num_calls):
                # Determine call outcome based on whether this lead will be reached
                if is_reached and attempt == (num_calls - 1):  # Final call reaches them
                    if is_appointment:
                        # This will be an appointment call
                        disconnection_reason = DisconnectionReason.AGENT_HANGUP
                        duration = random.randint(300, 900)  # 5-15 minutes for appointment calls
                        appointment_datetime = self._generate_appointment_time(month_end)
                    else:
                        # Reached but no appointment (interest but no booking)
                        disconnection_reason = DisconnectionReason.USER_HANGUP
                        duration = random.randint(120, 480)  # 2-8 minutes for reached without appointment
                        appointment_datetime = None
                    stats['reached_calls'] += 1
                    if is_appointment:
                        stats['appointment_calls'] += 1
                else:
                    # Not reached on this attempt
                    disconnection_reason = random.choice([
                        DisconnectionReason.DIAL_NO_ANSWER,
                        DisconnectionReason.DIAL_BUSY,
                        DisconnectionReason.VOICEMAIL_REACHED
                    ])
                    duration = random.randint(0, 45)  # Short duration for failed calls
                    appointment_datetime = None

                # Generate call time within the month (usually 1-7 days after lead created)
                days_after_lead = random.randint(1, min(7, (month_end - lead.created_at).days))
                call_time = lead.created_at + timedelta(
                    days=days_after_lead,
                    hours=random.randint(9, 17),  # Business hours
                    minutes=random.randint(0, 59)
                )

                # Create call log
                CallLog.objects.create(
                    workspace=workspace,
                    agent=agent,
                    lead=lead,
                    call_task_id=uuid.uuid4(),
                    target_ref=f"lead:{lead.id}",
                    timestamp=call_time,
                    from_number=agent.phone_number.phonenumber,
                    to_number=lead.phone,
                    duration=duration,
                    disconnection_reason=disconnection_reason,
                    direction='outbound',
                    appointment_datetime=appointment_datetime
                )

                stats['total_calls'] += 1

        return stats

    def _generate_monthly_test_calls(self, workspace, agent, count, month_start, month_end):
        """Generate test calls (calls without associated leads) for a month"""
        stats = {'test_calls': 0}

        test_numbers = [
            "+49123456789", "+49987654321", "+49555123456",
            "+49444987654", "+49333555777", "+49666888999",
            "+49111222333", "+49777888999", "+49666555444"
        ]

        for i in range(count):
            # Test calls are usually shorter and have various outcomes
            duration = random.randint(5, 180)

            outcome = random.choice([
                DisconnectionReason.USER_HANGUP,
                DisconnectionReason.DIAL_NO_ANSWER,
                DisconnectionReason.DIAL_BUSY,
                DisconnectionReason.AGENT_HANGUP
            ])

            # Random timestamp within the month
            call_time = month_start + timedelta(
                days=random.randint(0, (month_end - month_start).days),
                hours=random.randint(9, 18),  # Business hours + bit extra
                minutes=random.randint(0, 59)
            )

            CallLog.objects.create(
                workspace=workspace,
                agent=agent,
                lead=None,  # No lead for test calls
                call_task_id=uuid.uuid4(),
                target_ref=f"test_phone:{random.choice(test_numbers)}",
                timestamp=call_time,
                from_number=agent.phone_number.phonenumber,
                to_number=random.choice(test_numbers),
                duration=duration,
                disconnection_reason=outcome,
                direction='outbound'
            )

            stats['test_calls'] += 1

        return stats

    def _generate_appointment_time(self, after_date):
        """Generate a realistic appointment time in the future"""
        # Appointments are usually scheduled 3-21 days in the future
        days_ahead = random.randint(3, 21)
        appointment_date = after_date + timedelta(days=days_ahead)

        # Business hours appointments (9 AM - 5 PM, 15-minute slots)
        hour = random.randint(9, 16)
        minute = random.choice([0, 15, 30, 45])

        return appointment_date.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0
        )

