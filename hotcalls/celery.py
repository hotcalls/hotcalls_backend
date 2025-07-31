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
    # Clean up expired authentication tokens daily at midnight
    'cleanup-expired-tokens': {
        'task': 'core.tasks.cleanup_expired_tokens',
        'schedule': crontab(hour=0, minute=0),  # Run daily at midnight (00:00)
        'options': {
            'queue': 'celery'  # Use the same queue the worker is listening to
        }
    },
    # Schedule agent calls every second
    'schedule-agent-calls': {
        'task': 'core.tasks.schedule_agent_call',
        'schedule': 2.5,  # Run every 1 second
        'options': {
            'queue': 'celery',
            'expires': 5,  # Task expires after 5 seconds to prevent overlap
        }
    },
    # Clean up stuck call tasks every minute
    'cleanup-stuck-call-tasks': {
        'task': 'core.tasks.cleanup_stuck_call_tasks',
        'schedule': 60.0,  # Run every 1 minute (60 seconds)
        'options': {
            'queue': 'celery',
            'expires': 30,  # Task expires after 30 seconds to prevent overlap
        }
    },
} 