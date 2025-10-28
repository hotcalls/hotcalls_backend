"""
Migration settings for HotCalls project.
Minimal configuration for running build-time tasks like migrations and collectstatic.
"""

from pathlib import Path


SECRET_KEY = "asdnj32uidhinsfi9032r"
AUTH_USER_MODEL = "core.User"
BASE_DIR = Path(__file__).resolve().parent.parent.parent


INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework.authtoken",
    "django_celery_beat",
    "core",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "mydatabase",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
