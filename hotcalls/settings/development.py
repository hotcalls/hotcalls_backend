"""
Development settings for HotCalls project.

These settings are used for local development and testing using docker.
"""

from .base import *
import os


# App configuration
DEBUG = True
ALLOWED_HOSTS = ["*"]

# Security settings
SECURE_SSL_REDIRECT = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_CONTENT_TYPE_NOSNIFF = False
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

# CORS configuration
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite development server
    "http://127.0.0.1:5173",
    "http://localhost:5175",  # Alternative Vite port
    "http://127.0.0.1:5175",
    "http://localhost:8080",  # Vue development server
    "http://127.0.0.1:8080",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "range",
]
CORS_EXPOSE_HEADERS = [
    "content-length",
    "content-range",
    "accept-ranges",
]

# Session Configuration
SESSION_COOKIE_AGE = 86400
SESSION_COOKIE_HTTPONLY = False
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = True

# CSRF Configuration
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",  # Vite development server
    "http://127.0.0.1:5173",
    "http://localhost:5175",  # Alternative Vite port
    "http://127.0.0.1:5175",
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
]

# Static configuration
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# Media configuration
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Development-specific apps
INSTALLED_APPS += [
    "django_extensions",
]

# Development toolbar
try:
    import debug_toolbar

    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
    INTERNAL_IPS = ["127.0.0.1", "0.0.0.0"]
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
    }
except ImportError:
    pass

# Cache configuration
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Debug logging for development and file logging
LOGGING["handlers"]["console"]["level"] = "DEBUG"
LOGGING["handlers"]["django_file"] = {
    "level": "INFO",
    "class": "logging.FileHandler",
    "filename": "django_info.log",
    "formatter": "verbose",
}
LOGGING["handlers"]["hotcalls_file"] = {
    "level": "INFO",
    "class": "logging.FileHandler",
    "filename": "hotcalls_info.log",
    "formatter": "verbose",
}

LOGGING["handlers"]["core_file"] = {
    "level": "INFO",
    "class": "logging.FileHandler",
    "filename": "app_core_info.log",
    "formatter": "verbose",
}

LOGGING["loggers"]["hotcalls"]["handlers"] = ["console", "hotcalls_file"]
LOGGING["loggers"]["django"]["handlers"] = ["console", "django_file"]
LOGGING["loggers"]["core"]["handlers"] = ["console", "core_file"]


# Django extensions configuration
SHELL_PLUS = "ipython"
SHELL_PLUS_PRINT_SQL = True

# Rest framework settings for development
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [
    "rest_framework.renderers.BrowsableAPIRenderer",
]
