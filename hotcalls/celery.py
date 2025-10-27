import os
from celery import Celery
from django.conf import settings
from celery.schedules import crontab

# Create the Celery app
app = Celery("hotcalls")

# Load Celery configuration from Django Settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks from all installed apps
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Set time limit for tasks. 1 hour hard limit and 50min soft limit
app.conf.task_time_limit = 3600
app.conf.task_soft_time_limit = 3000

# Configure worker settings to handle connection issues
app.conf.broker_connection_retry = True
app.conf.broker_connection_retry_on_startup = True
app.conf.broker_connection_max_retries = 10

# Configure worker settings for tasks
app.conf.worker_concurrency = 4
app.conf.worker_prefetch_multiplier = 1
app.conf.worker_max_tasks_per_child = 100

# Configure worker settings for timeouts
app.conf.worker_lost_wait = 30
app.conf.broker_connection_timeout = 30

# Periodic task configuration
app.conf.beat_schedule = {
    # Schedule agent calls, every 5 seconds. Expires after 2.5 seconds
    "schedule-agent-calls": {
        "task": "core.tasks.schedule_agent_call",
        "schedule": 5.0,
        "options": {
            "queue": "celery",
            "expires": 2.5,
        },
    },
    # Clean up stuck call tasks, every minute. Expires after 2 minutes
    "cleanup-stuck-call-tasks": {
        "task": "core.tasks.cleanup_stuck_call_tasks",
        "schedule": 60.0,
        "options": {
            "queue": "celery",
            "expires": 120,
        },
    },
    # Clean up router subaccounts, every 5 minutes. Expires after 5 minutes
    "cleanup-router-subaccounts": {
        "task": "core.tasks.cleanup_orphan_router_subaccounts",
        "schedule": 300.0,
        "options": {
            "queue": "celery",
            "expires": 300,
        },
    },
    # Sync Meta lead form to keep updated, daily at 00:00
    "daily-meta-sync": {
        "task": "core.tasks.daily_meta_sync",
        "schedule": crontab(hour=0, minute=0),
        "options": {"queue": "celery"},
    },
    # Try to discover new sub-accounts, daily at 3:00 AM
    "refresh-calendar-subaccounts-daily": {
        "task": "core.tasks.refresh_calendar_subaccounts",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "celery"},
    },
    # Try to refresh soon expiring Meta tokens weekly, sunday at 2:00 AM
    "refresh-meta-tokens-weekly": {
        "task": "core.tasks.refresh_meta_tokens",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
        "options": {"queue": "celery"},
    },
    # Try to refresh soon expiring Google tokens weekly, sunday at 2:15 AM
    "refresh-google-tokens-weekly": {
        "task": "core.tasks.refresh_google_calendar_connections",
        "schedule": crontab(hour=2, minute=15, day_of_week=0),
        "options": {"queue": "celery"},
    },
    # Try to refresh soon expiring Outlook tokens weekly, sunday at 2:30 AM
    "refresh-outlook-tokens-weekly": {
        "task": "core.tasks.refresh_microsoft_calendar_connections",
        "schedule": crontab(hour=2, minute=30, day_of_week=0),
        "options": {"queue": "celery"},
    },
    # Clean up inactive google calendars weekly, sunday at 4:00 AM
    "cleanup-google-calendars-weekly": {
        "task": "core.tasks.cleanup_invalid_google_connections",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
        "options": {"queue": "celery"},
    },
    # Clean up inactive outlook calendars weekly, sunday at 4:15 AM
    "cleanup-outlook-calendars-weekly": {
        "task": "core.tasks.cleanup_invalid_outlook_connections",
        "schedule": crontab(hour=4, minute=15, day_of_week=0),
        "options": {"queue": "celery"},
    },
    # Clean up invalid meta integrations weekly, sunday at 4:30 AM
    "cleanup-invalid-meta-weekly": {
        "task": "core.tasks.cleanup_invalid_meta_integrations",
        "schedule": crontab(hour=4, minute=30, day_of_week=0),
        "options": {"queue": "celery"},
    },
}
