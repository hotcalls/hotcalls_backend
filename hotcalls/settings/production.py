"""
Production settings for HotCalls project.

These settings are optimized for Azure deployment with security, performance,
and monitoring in mind.
"""

from .base import *
import os
import sys
import logging

# Setup logging
logger = logging.getLogger(__name__)
logger.info(f"Loaded {__name__} settings module")

# Production environment identifier
ENVIRONMENT = 'production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
    raise ValueError("ALLOWED_HOSTS must be set in production")

# Security settings (strict for production)
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() == "true"
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "True").lower() == "true"
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "True").lower() == "true"
SECURE_BROWSER_XSS_FILTER = os.environ.get("SECURE_BROWSER_XSS_FILTER", "True").lower() == "true"
SECURE_CONTENT_TYPE_NOSNIFF = os.environ.get("SECURE_CONTENT_TYPE_NOSNIFF", "True").lower() == "true"
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

# Additional security headers
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# CORS Settings (configurable for production)
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "False").lower() == "true"
cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins.split(",") if origin.strip()] if cors_origins else []
CORS_ALLOW_CREDENTIALS = True

# Azure Blob Storage configuration
AZURE_ACCOUNT_NAME = os.environ.get('AZURE_ACCOUNT_NAME')
AZURE_STORAGE_KEY = os.environ.get('AZURE_STORAGE_KEY')
AZURE_STATIC_CONTAINER = os.environ.get('AZURE_STATIC_CONTAINER', 'static')
AZURE_MEDIA_CONTAINER = os.environ.get('AZURE_MEDIA_CONTAINER', 'media')
AZURE_CUSTOM_DOMAIN = os.environ.get('AZURE_CUSTOM_DOMAIN')

if AZURE_ACCOUNT_NAME and AZURE_STORAGE_KEY:
    # Use Azure Blob Storage for static and media files
    DEFAULT_FILE_STORAGE = 'hotcalls.storage_backends.AzureMediaStorage'
    STATICFILES_STORAGE = 'hotcalls.storage_backends.AzureStaticStorage'
    
    if AZURE_CUSTOM_DOMAIN:
        # Use CDN endpoint if available
        STATIC_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_STATIC_CONTAINER}/"
        MEDIA_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_MEDIA_CONTAINER}/"
    else:
        # Use blob storage endpoint directly
        STATIC_URL = f"https://{AZURE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_STATIC_CONTAINER}/"
        MEDIA_URL = f"https://{AZURE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_MEDIA_CONTAINER}/"
else:
    # Fallback to local storage with whitenoise
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    STATIC_URL = '/static/'
    MEDIA_URL = '/media/'

STATIC_ROOT = BASE_DIR / 'staticfiles'

# Database configuration with SSL for production
DATABASES['default']['OPTIONS'].update({
    'sslmode': 'require',  # Require SSL for production database
})

# Database settings come from base.py which now FAILS FAST if not set
# No overrides needed - base.py handles environment detection properly

# Azure Application Insights configuration
AZURE_MONITOR_CONNECTION_STRING = os.environ.get('AZURE_MONITOR_CONNECTION_STRING')
if AZURE_MONITOR_CONNECTION_STRING:
    from azure.monitor.opentelemetry import configure_azure_monitor
    # Configure Application Insights
    configure_azure_monitor(
        connection_string=AZURE_MONITOR_CONNECTION_STRING,
    )

# Cache configuration using Redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 20,
                'retry_on_timeout': True,
            },
        },
        'KEY_PREFIX': 'hotcalls',
        'TIMEOUT': 300,  # 5 minutes default timeout
    }
}

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Email configuration for production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@hotcalls.com')

# Logging for production
LOGGING['formatters']['verbose']['format'] = (
    '{levelname} {asctime} {module} {process:d} {thread:d} {message}'
)

# Add structured logging for Azure
LOGGING['handlers']['azure'] = {
    'class': 'logging.StreamHandler',
    'stream': sys.stdout,
    'formatter': 'verbose',
}

LOGGING['loggers'].update({
    'azure': {
        'handlers': ['azure'],
        'level': 'INFO',
        'propagate': False,
    },
    'gunicorn': {
        'handlers': ['console'],
        'level': 'INFO',
        'propagate': False,
    },
})

# REST Framework settings for production
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# Disable browsable API in production
REST_FRAMEWORK.pop('DEFAULT_RENDERER_CLASSES', None)

# Performance optimizations
CONN_MAX_AGE = 60  # Keep database connections alive for 60 seconds

# Security middleware additions
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # If using whitenoise
] + MIDDLEWARE[1:]

# Health check apps for Kubernetes
INSTALLED_APPS += [
    'health_check.contrib.migrations',
] 