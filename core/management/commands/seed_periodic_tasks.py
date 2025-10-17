from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Seed periodic tasks for Celery Beat. Idempotent."

    def handle(self, *args, **options):
        self.stdout.write("Seeding periodic tasks...")

        # Helper to ensure/update a periodic task by interval (seconds)
        def ensure_interval_task(name, task, every_seconds, enabled=True):
            sched, _ = IntervalSchedule.objects.get_or_create(
                every=every_seconds,
                period=IntervalSchedule.SECONDS
            )
            periodic_task, created = PeriodicTask.objects.update_or_create(
                name=name,
                defaults={
                    "task": task,
                    "interval": sched,
                    "enabled": enabled
                }
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {name} ({task}) every {every_seconds}s")

        # Schedule agent calls every 5s
        ensure_interval_task(
            "schedule-agent-calls",
            "core.tasks.schedule_agent_call",
            5,
            True
        )

        # Cleanup stuck call tasks every 60s
        ensure_interval_task(
            "cleanup-stuck-call-tasks",
            "core.tasks.cleanup_stuck_call_tasks",
            60,
            True
        )

        # Cleanup router subaccounts every 300s (5 minutes)
        ensure_interval_task(
            "cleanup-router-subaccounts",
            "core.tasks.cleanup_orphan_router_subaccounts",
            300,
            True
        )

        self.stdout.write(self.style.SUCCESS("Periodic tasks ensured."))
