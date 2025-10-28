"""
Base settings for hotcalls project.
Containing common settings across all environments.
Environment-specific settings inherit from this base configuration.
"""

import os
from pathlib import Path
import logging

# Setup logging for settings module
logger = logging.getLogger(__name__)

# Load data from environment. Use os.environ[...] to ensure a key error is raised when 1 is missing. Key error results in RuntimeError
try:
    ENVIRONMENT = os.environ["ENVIRONMENT"]
    SECRET_KEY = os.environ["SECRET_KEY"]

    # Base App configuration
    TIME_ZONE = os.environ["TIME_ZONE"]
    BASE_URL = os.environ["BASE_URL"]
    csrf_trusted_origins = os.environ["CSRF_TRUSTED_ORIGINS"]

    # Database configuration
    DB_ENGINE = os.environ["DB_ENGINE"]
    DB_NAME = os.environ["DB_NAME"]
    DB_USER = os.environ["DB_USER"]
    DB_PASSWORD = os.environ["DB_PASSWORD"]
    DB_HOST = os.environ["DB_HOST"]
    DB_PORT = os.environ["DB_PORT"]
    DB_SSL_MODE = os.environ["DB_SSLMODE"]

    # Redis configuration
    REDIS_HOST = os.environ["REDIS_HOST"]
    REDIS_PASSWORD = os.environ["REDIS_PASSWORD"]
    REDIS_PORT = os.environ["REDIS_PORT"]
    REDIS_DB = os.environ["REDIS_DB"]
    REDIS_URL = os.environ["REDIS_URL"]

    # Celery configuration
    CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]
    CELERY_RESULT_BACKEND = os.environ["CELERY_RESULT_BACKEND"]

    # Email Configuration
    EMAIL_BACKEND = os.environ["EMAIL_BACKEND"]
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = os.environ["EMAIL_PORT"]
    EMAIL_USE_TLS = os.environ["EMAIL_USE_TLS"]
    EMAIL_USE_SSL = os.environ["EMAIL_USE_SSL"]
    EMAIL_HOST_USER = os.environ["EMAIL_HOST_USER"]
    EMAIL_HOST_PASSWORD = os.environ["EMAIL_HOST_PASSWORD"]
    DEFAULT_FROM_EMAIL = os.environ["DEFAULT_FROM_EMAIL"]
    SERVER_EMAIL = os.environ["SERVER_EMAIL"]

    # Stripe configuration
    STRIPE_SECRET_KEY = os.environ["STRIPE_SECRET_KEY"]
    STRIPE_PUBLISHABLE_KEY = os.environ["STRIPE_PUBLISHABLE_KEY"]
    STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
    STRIPE_MINUTE_PACK_PRICE_ID = os.environ["STRIPE_MINUTE_PACK_PRICE_ID"]
    STRIPE_MINUTE_PACK_PRODUCT_ID = os.environ["STRIPE_MINUTE_PACK_PRODUCT_ID"]

    # Meta Integration
    META_APP_ID = os.environ["META_APP_ID"]
    META_APP_SECRET = os.environ["META_APP_SECRET"]
    META_WEBHOOK_VERIFY_TOKEN = os.environ["META_WEBHOOK_VERIFY_TOKEN"]
    META_API_VERSION = os.environ["META_API_VERSION"]
    META_REDIRECT_URI = os.environ["META_REDIRECT_URI"]

    # LiveKit Configuration
    LIVEKIT_URL = os.environ["LIVEKIT_URL"]
    LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
    LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
    LIVEKIT_AGENT_NAME = os.environ["LIVEKIT_AGENT_NAME"]
    NUMBER_OF_LIVEKIT_AGENTS = os.environ["NUMBER_OF_LIVEKIT_AGENTS"]
    CONCURRENCY_PER_LIVEKIT_AGENT = os.environ["CONCURRENCY_PER_LIVEKIT_AGENT"]

    # Google configuration
    GOOGLE_OAUTH_CLIENT_ID = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]

    # Microsoft configuration
    MS_CLIENT_ID = os.environ["MS_CLIENT_ID"]
    MS_CLIENT_SECRET = os.environ["MS_CLIENT_SECRET"]
    MS_AUTH_TENANT = os.environ["MS_AUTH_TENANT"]

    # OpenAI Configuration
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
except KeyError as e:
    missing_variable = e.args[0]
    raise RuntimeError(f"Environment variable {missing_variable} is not set")


# Base App setup
API_VERSION = "v1"
LANGUAGE_CODE = "en-us"
USE_I18N = True
USE_TZ = True
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in csrf_trusted_origins.split(",") if origin.strip()
]
ADMINS = [("Paul Bahr", "paul.bahr@malmachen.com")]

# Database configuration
DATABASES = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": {
            "sslmode": DB_SSL_MODE,
        },
    }
}
# Default primary key type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery configuration
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Google configuration
GOOGLE_REDIRECT_URI = f"{BASE_URL}/api/google-calendar/auth/callback/"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# Microsoft configuration
MS_REDIRECT_URI = f"{BASE_URL}/api/outlook-calendar/auth/callback/"
MS_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Calendars.ReadWrite",
    "Calendars.Read.Shared",
    "Calendars.ReadWrite.Shared",
    "MailboxSettings.Read",
    "OnlineMeetings.Read",
    "OnlineMeetings.ReadWrite",
]

# File upload configuration
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024  # 1GB
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024  # 1GB
FILE_UPLOAD_TEMP_DIR = None
FILE_UPLOAD_PERMISSIONS = 0o644
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# User Model
AUTH_USER_MODEL = "core.User"

# Email based authentication backend
AUTHENTICATION_BACKENDS = [
    "core.management_api.auth_api.backends.EmailBackend",
]

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_celery_beat",
    "drf_spectacular",
    "django_filters",
]

LOCAL_APPS = [
    "core",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.PlanQuotaMiddleware",  # Quota enforcement after authentication
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hotcalls.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "hotcalls.context_processors.base_url",
            ],
        },
    },
]

WSGI_APPLICATION = "hotcalls.wsgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

# Spectacular (OpenAPI/Swagger) Settings
API_DESCRIPTION = (Path(__file__).parent / "spectacular_api_description.md").read_text()

SPECTACULAR_SETTINGS = {
    "TITLE": "HotCalls API",
    "DESCRIPTION": API_DESCRIPTION,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "TAGS": [
        {
            "name": "Authentication",
            "description": "Token-based authentication with mandatory email verification",
        },
        {
            "name": "User Management",
            "description": "User accounts and blacklist management - Requires token auth",
        },
        {
            "name": "Workspace Management",
            "description": "Workspace and user association management",
        },
        {
            "name": "Agent Management",
            "description": "AI agents and phone number management",
        },
        {
            "name": "Lead Management",
            "description": "Lead management and bulk operations",
        },
    ],
    "COMPONENT_SECURITY_SCHEMES": {
        "TokenAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Token-based authentication. Format: `Token <your-token>`",
        }
    },
    "SECURITY": [{"TokenAuth": []}],
}

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {funcName:s} {message}",
            "style": "{",
        },
        "basic": {
            "format": "{levelname} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "basic",
        },
        "django_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "django_info.log",
            "formatter": "verbose",
        },
        "hotcalls_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "hotcalls_info.log",
            "formatter": "verbose",
        },
        "core_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "hotcalls_info.log",
            "formatter": "verbose",
        },
        "email_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
    },
    "loggers": {
        "hotcalls": {
            "handlers": ["console", "hotcalls_file", "email_admins"],
            "propagate": False,
        },
        "django": {
            "handlers": ["console", "django_file"],
            "propagate": False,
        },
        "core": {
            "handlers": ["console", "core_file", "email_admins"],
            "propagate": False,
        },
    },
}
