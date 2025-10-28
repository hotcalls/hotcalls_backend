"""
Staging settings for HotCalls project.
"""

from .base import *
import os
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Load data from environment. Use os.environ[...] to ensure a key error is raised when 1 is missing. Key error results in RuntimeError
try:
    ALLOWED_HOSTS = [os.environ["ALLOWED_HOSTS"]]

    # Security configuration
    SECURE_SSL_REDIRECT = os.environ["SECURE_SSL_REDIRECT"].lower() == "true"
    SESSION_COOKIE_SECURE = os.environ["SESSION_COOKIE_SECURE"].lower() == "true"
    CSRF_COOKIE_SECURE = os.environ["CSRF_COOKIE_SECURE"].lower() == "true"
    SECURE_BROWSER_XSS_FILTER = (
        os.environ["SECURE_BROWSER_XSS_FILTER"].lower() == "true"
    )
    SECURE_CONTENT_TYPE_NOSNIFF = (
        os.environ["SECURE_CONTENT_TYPE_NOSNIFF"].lower() == "true"
    )
    X_FRAME_OPTIONS = os.environ["X_FRAME_OPTIONS"]

    # Storage account configuration
    AZURE_ACCOUNT_NAME = os.environ["AZURE_ACCOUNT_NAME"]
    AZURE_STORAGE_KEY = os.environ["AZURE_STORAGE_KEY"]
    AZURE_CUSTOM_DOMAIN = os.environ["AZURE_CUSTOM_DOMAIN"]

    SERVE_STATIC_VIA_BACKEND = os.environ["SERVE_STATIC_VIA_BACKEND"].lower() == "true"
except KeyError as e:
    missing_variable = e.args[0]
    raise RuntimeError(f"Environment variable {missing_variable} is not set")

# Azure container names
AZURE_MEDIA_CONTAINER = "media"
AZURE_STATIC_CONTAINER = "static"

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Disable SSL redirect for localhost/port-forwarding
if SECURE_SSL_REDIRECT:
    import socket

    hostname = socket.gethostname()
    # Disable for local development and port-forwarding
    if "localhost" in hostname or "127.0.0.1" in hostname:
        SECURE_SSL_REDIRECT = False

SECURE_REDIRECT_EXEMPT = [
    r"^health/$",
    r"^health$",
    r"^admin/",
    r"^static/",
]

# CORS configuration
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_METHODS = ["*"]


# Static configuration
# Optional local static with whitenoise for save admin port-forward, or azure storage for static
if SERVE_STATIC_VIA_BACKEND:
    STATIC_URL = "/static/"
    STATIC_ROOT = BASE_DIR / "staticfiles"

    # Ensure middleware present early for efficient static serving
    if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
        MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

    STORAGES = {
        "default": {
            "BACKEND": "hotcalls.storage_backends.AzureMediaStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }

    MEDIA_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_MEDIA_CONTAINER}/"
else:
    # Use azure storage for media and static
    STORAGES = {
        "default": {
            "BACKEND": "hotcalls.storage_backends.AzureMediaStorage",
        },
        "staticfiles": {
            "BACKEND": "hotcalls.storage_backends.AzureStaticStorage",
        },
    }

    STATIC_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_STATIC_CONTAINER}/"
    MEDIA_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_MEDIA_CONTAINER}/"

# Cache configuration
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
        },
        "KEY_PREFIX": "hotcalls_staging",
        "TIMEOUT": 300,
    }
}
