"""
Base Django settings for HotCalls project.

This module contains settings that are common across all environments.
Environment-specific settings inherit from this base configuration.
"""

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
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-=a8o!^u&0e(!-p_$f)ppq2r=*)$g8v(3lrb*vl@+b%i!pn8-=r"
)

# Custom User Model
AUTH_USER_MODEL = 'core.User'

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
    "corsheaders",
    "django_celery_beat",
    "drf_yasg",
    "drf_spectacular",
    "django_filters",
    "health_check",
    "health_check.db",
    "health_check.cache",
    "health_check.storage",
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
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hotcalls.urls"

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hotcalls.wsgi.application'

# Database configuration
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.environ.get('DB_NAME', 'hotcalls_db'),
        'USER': os.environ.get('DB_USER', 'hotcalls_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': os.environ.get('DB_SSLMODE', 'prefer'),
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get("TIME_ZONE", "Europe/Berlin")
USE_I18N = True
USE_TZ = True

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# Spectacular (OpenAPI/Swagger) Settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'HotCalls API',
    'DESCRIPTION': '''
# 🔐 HotCalls API - Complete Permission Matrix

## 🎭 User Roles & Authentication

### User Role Hierarchy
| Role | Level | Description | Permissions |
|------|--------|-------------|-------------|
| **👤 Regular User** | `is_authenticated=True` | Standard authenticated user | Limited to own data and workspace resources |
| **👔 Staff Member** | `is_staff=True` | System staff member | Can manage most system resources |
| **🔧 Superuser** | `is_superuser=True` | System administrator | Full access to all operations |

### 🔑 Authentication Methods
- **Session Authentication**: Login via `/admin/` then use session cookies
- **Basic Authentication**: Use `Authorization: Basic <base64(username:password)>` header

---

## 📊 Complete Permission Matrix

[Rest of the spectacular settings content from original settings.py]
    ''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/',
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': False,
    'TAGS': [
        {'name': 'User Management', 'description': '👤 User accounts and blacklist management - Role-based access to user data'},
        {'name': 'Subscription Management', 'description': '📋 Plans, features, and subscription management - Staff manage, Users view'},
        {'name': 'Workspace Management', 'description': '🏢 Workspace and user association management - Workspace-filtered access'},
        {'name': 'Agent Management', 'description': '🤖 AI agents and phone number management - Workspace-scoped agent access'},
        {'name': 'Lead Management', 'description': '📞 Lead management and bulk operations - Shared lead access with staff controls'},
        {'name': 'Call Management', 'description': '📱 Call logs and analytics - Universal read access, staff write access'},
        {'name': 'Calendar Management', 'description': '📅 Calendar integration and scheduling - Workspace-filtered calendar access'},
    ],
}

# Celery Configuration - Dynamically constructed from Redis env vars
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_DB = os.environ.get("REDIS_DB", "0")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")

# Construct Redis URL with optional password
if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Base URL for generating absolute URLs
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'hotcalls': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Health check configuration
HEALTH_CHECK = {
    'DISK_USAGE_MAX': 90,  # Fail if disk usage is over 90%
    'MEMORY_MIN': 100,     # Fail if available memory is less than 100MB
}

# API configuration
API_VERSION = 'v1' 