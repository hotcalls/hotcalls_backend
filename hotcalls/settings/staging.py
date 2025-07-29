"""
Staging settings for HotCalls project.

These settings are for the staging environment deployed on Azure Kubernetes.
Similar to production but may have different debug/logging levels.
"""

from .base import *
import os
import logging

# Setup logging
logger = logging.getLogger(__name__)
logger.info(f"Loaded {__name__} settings module")

# Staging environment identifier
ENVIRONMENT = 'staging'

# Debug should always be True for staging to help troubleshoot issues
DEBUG = False  # Set to False for more production-like behavior

# ALLOWED_HOSTS - ALWAYS use wildcard per user requirement
ALLOWED_HOSTS = ["*"]

# Security settings for staging (can be less strict than production)
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "False").lower() == "true"
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "False").lower() == "true"
SECURE_BROWSER_XSS_FILTER = os.environ.get("SECURE_BROWSER_XSS_FILTER", "True").lower() == "true"
SECURE_CONTENT_TYPE_NOSNIFF = os.environ.get("SECURE_CONTENT_TYPE_NOSNIFF", "True").lower() == "true"
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

# CSRF - COMPLETELY DISABLED FOR STAGING
# WARNING: This removes ALL CSRF protection - NEVER use in production!
# This modifies the MIDDLEWARE list from base.py to remove CSRF
MIDDLEWARE = list(MIDDLEWARE)  # Convert tuple to list if needed
if 'django.middleware.csrf.CsrfViewMiddleware' in MIDDLEWARE:
    MIDDLEWARE.remove('django.middleware.csrf.CsrfViewMiddleware')

# CORS - COMPLETELY OPEN FOR STAGING
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_METHODS = ["*"]

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Database configuration - uses environment variables from K8s secrets
# No need to override here - base.py already reads from os.environ
# Just ensure SSL mode is set appropriately for Azure PostgreSQL
DATABASES['default']['OPTIONS'].update({
    'sslmode': os.environ.get('DB_SSLMODE', 'require'),
})

# Cache configuration for staging
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
        },
        'KEY_PREFIX': 'hotcalls_staging',
        'TIMEOUT': 300,
    }
}

# Logging configuration for staging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
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
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'hotcalls': {
            'handlers': ['console'],
            'level': 'DEBUG',  # More verbose logging for staging
            'propagate': False,
        },
    },
}

# Email configuration remains the same (from base.py environment variables)
# No need to override unless staging uses different email settings

# Celery configuration remains the same (from base.py)
# Uses Redis from environment variables 