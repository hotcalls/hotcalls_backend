# This will make sure the app is always imported when Django starts
try:
    from .celery import app as celery_app
    __all__ = ['celery_app']
except ImportError:
    # Skip celery import for testing environments
    __all__ = []
