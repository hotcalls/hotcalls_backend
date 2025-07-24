import os
from pathlib import Path
import logging
from dotenv import load_dotenv

# Setup logging for settings module
logger = logging.getLogger(__name__)

# Load environment variables from .env file - with error handling
try:
    load_dotenv()
except Exception as e:
    logger.warning(f"Failed to load .env file: {str(e)}")
    logger.warning("Continuing with default environment variables")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-=a8o!^u&0e(!-p_$f)ppq2r=*)$g8v(3lrb*vl@+b%i!pn8-=r"
)
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

TIME_ZONE = os.environ.get("TIME_ZONE", "Europe/Berlin")
USE_TZ = True

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "False").lower() == "true"
SESSION_COOKIE_SECURE = (
    os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
)
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "False").lower() == "true"
SECURE_BROWSER_XSS_FILTER = (
    os.environ.get("SECURE_BROWSER_XSS_FILTER", "False").lower() == "true"
)
SECURE_CONTENT_TYPE_NOSNIFF = (
    os.environ.get("SECURE_CONTENT_TYPE_NOSNIFF", "False").lower() == "true"
)
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

STATIC_URL = os.environ.get("STATIC_URL", "static/")
STATIC_ROOT = BASE_DIR / "staticfiles"
ROOT_URLCONF = "hotcalls.urls"


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "core",
    "django_celery_beat",
    "drf_yasg",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = (
    os.environ.get("CORS_ALLOW_ALL_ORIGINS", "True").lower() == "true"
)


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

DATABASES = {}

TEMPLATES = []

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
}


LOGGING = {
}

# Celery Configuration
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "rpc://")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE


# Base URL for generating absolute URLs
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
