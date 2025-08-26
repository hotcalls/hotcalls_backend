import os
from celery import Celery
from django.conf import settings
from celery.schedules import crontab

# Set the default Django settings module to the correct one
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotcalls.settings')

# Create the Celery app
app = Celery('hotcalls')

# Load configuration from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Discover tasks in all installed apps
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Configure task-specific settings
app.conf.task_time_limit = int(os.environ.get('CELERY_TASK_TIME_LIMIT', 3600))  # Default 1 hour timeout
app.conf.task_soft_time_limit = int(os.environ.get('CELERY_TASK_SOFT_TIME_LIMIT', 3000))  # Default 50 minutes soft timeout

# Configure worker settings to handle connection issues
app.conf.broker_connection_retry = True
app.conf.broker_connection_retry_on_startup = True
app.conf.broker_connection_max_retries = 10
app.conf.worker_lost_wait = 30  # Seconds to wait for a worker to respond before it's considered lost
app.conf.worker_concurrency = int(os.environ.get('CELERY_WORKER_CONCURRENCY', 4))
app.conf.worker_prefetch_multiplier = 1  # Reduce prefetching to avoid overwhelming the worker

# Enable automatic worker restart on failure
app.conf.worker_max_tasks_per_child = int(os.environ.get('CELERY_MAX_TASKS_PER_CHILD', 100))
app.conf.broker_connection_timeout = 30  # Connection timeout in seconds

# Configure the periodic tasks
app.conf.beat_schedule = {

    # Schedule agent calls every 5 seconds
    'schedule-agent-calls': {
        'task': 'core.tasks.schedule_agent_call',
        'schedule': 5.0,  # Run every 5 seconds
        'options': {
            'queue': 'celery',
            'expires': 2.5,  # Task expires after 2.5 seconds (aggressive backpressure)
        }
    },
    
    # ===== OAUTH TOKEN MANAGEMENT - WEEKLY ON SUNDAYS =====
    
    # Refresh Meta OAuth tokens 30 days before expiry
    'refresh-meta-tokens-weekly': {
        'task': 'core.tasks.refresh_meta_tokens',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),  # Weekly on Sunday at 2:00 AM
        'options': {
            'queue': 'celery'
        }
    },
    
    # Refresh Google OAuth tokens 30 days before expiry
    'refresh-google-tokens-weekly': {
        'task': 'core.tasks.refresh_google_calendar_connections',
        'schedule': crontab(hour=2, minute=15, day_of_week=0),  # Weekly on Sunday at 2:15 AM
        'options': {
            'queue': 'celery'
        }
    },
    # Refresh Outlook OAuth tokens 30 days before expiry
    'refresh-outlook-tokens-weekly': {
        'task': 'core.tasks.refresh_microsoft_calendar_connections',
        'schedule': crontab(hour=2, minute=30, day_of_week=0),  # Weekly on Sunday at 2:30 AM
        'options': {
            'queue': 'celery'
        }
    },
    
    # Discover new sub-accounts (shared/delegated calendars) - DAILY for good UX
    'refresh-calendar-subaccounts-daily': {
        'task': 'core.tasks.refresh_calendar_subaccounts',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3:00 AM
        'options': {
            'queue': 'celery'
        }
    },
    
    # Clean up invalid calendars - WEEKLY
    'cleanup-google-calendars-weekly': {
        'task': 'core.tasks.cleanup_invalid_google_connections',
        'schedule': crontab(hour=4, minute=0, day_of_week=0),  # Weekly on Sunday at 4:00 AM
        'options': {
            'queue': 'celery'
        }
    },
    'cleanup-outlook-calendars-weekly': {
        'task': 'core.tasks.cleanup_invalid_outlook_connections',
        'schedule': crontab(hour=4, minute=15, day_of_week=0),  # Weekly on Sunday at 4:15 AM
        'options': {
            'queue': 'celery'
        }
    },
    
    # Clean up invalid Meta integrations - WEEKLY
    'cleanup-invalid-meta-weekly': {
        'task': 'core.tasks.cleanup_invalid_meta_integrations',
        'schedule': crontab(hour=4, minute=30, day_of_week=0),  # Weekly on Sunday at 4:30 AM
        'options': {
            'queue': 'celery'
        }
    },

    
    # Sync Meta lead forms daily to keep them up to date
    'daily-meta-sync': {
        'task': 'core.tasks.daily_meta_sync',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight (00:00)
        'options': {
            'queue': 'celery'
        }
    },
    
    # Clean up stuck call tasks every minute
    'cleanup-stuck-call-tasks': {
        'task': 'core.tasks.cleanup_stuck_call_tasks',
        'schedule': 60.0,  # Run every 1 minute (60 seconds)
        'options': {
            'queue': 'celery',
            'expires': 120,  # Task expires after 2 minutes (2x schedule interval)
        }
    },

} 