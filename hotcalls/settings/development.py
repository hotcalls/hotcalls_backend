"""
Development settings for HotCalls project.

These settings are used for local development and testing using docker.
"""

from .base import *
import os

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# ALLOWED_HOSTS - ALWAYS use wildcard per user requirement
ALLOWED_HOSTS = ["*"]

# Security settings (relaxed for development)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

# CORS Settings (permissive for development)
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite development server (actual port)
    "http://127.0.0.1:5173",
    "http://localhost:5175",  # Alternative Vite port
    "http://127.0.0.1:5175",
    "http://localhost:8080",  # Vue development server
    "http://127.0.0.1:8080",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'range',
]
CORS_EXPOSE_HEADERS = [
    'content-length',
    'content-range',
    'accept-ranges',
]

# Session Configuration for Cookie Authentication
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = False  # Allow JavaScript access for debugging
SESSION_COOKIE_SECURE = False  # False for development (HTTP)
SESSION_COOKIE_SAMESITE = 'Lax'  # Allow cross-site requests
SESSION_SAVE_EVERY_REQUEST = True

# CSRF Configuration for development
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript access
CSRF_COOKIE_SECURE = False  # False for development (HTTP)  
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",  # Vite development server (actual port)
    "http://127.0.0.1:5173",
    "http://localhost:5175",  # Alternative Vite port
    "http://127.0.0.1:5175",
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
]

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Removed STATICFILES_DIRS since we don't have a static directory
# All static files come from Django and third-party packages

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

# Email backend for development - USE .ENV CONFIGURATION
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # DISABLED - using .env instead

# Cache configuration (use Redis for development to match production)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

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

# Use PostgreSQL and Redis from .env configuration (Docker setup)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
