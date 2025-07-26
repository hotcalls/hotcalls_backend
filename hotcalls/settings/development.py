"""
Development settings for HotCalls project.

These settings are used for local development and should never be used in production.
"""

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")

# Security settings (relaxed for development)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

# CORS Settings (permissive for development)
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "True").lower() == "true"
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:8080",  # Vue development server
    "http://127.0.0.1:8080",
]
CORS_ALLOW_CREDENTIALS = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Development-specific apps
INSTALLED_APPS += [
    'django_extensions',
]

# Development toolbar (if available)
try:
    import debug_toolbar
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
    INTERNAL_IPS = ['127.0.0.1', '0.0.0.0']
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
    }
except ImportError:
    pass

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Cache configuration (use Redis for development to match production)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 10,
                'retry_on_timeout': True,
            },
        },
        'KEY_PREFIX': 'hotcalls_dev',
        'TIMEOUT': 300,  # 5 minutes default timeout
    }
}

# Database configuration (can be overridden by environment variables)
if os.environ.get('DB_HOST') != 'db':  # Not using Docker
    DATABASES['default'].update({
        'HOST': 'localhost',
        'OPTIONS': {
            'sslmode': 'disable',  # Disable SSL for local development
        }
    })

# Logging for development
LOGGING['loggers']['django']['level'] = 'DEBUG'
LOGGING['loggers']['hotcalls']['level'] = 'DEBUG'

# Django extensions configuration
SHELL_PLUS = "ipython"
SHELL_PLUS_PRINT_SQL = True

# Rest framework settings for development
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] += [
    'rest_framework.renderers.BrowsableAPIRenderer',
] 