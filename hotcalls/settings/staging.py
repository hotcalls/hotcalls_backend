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
    csrf_trusted_origins = os.environ["CSRF_TRUSTED_ORIGINS"]
    cors_allowed_origins = os.environ["CORS_ALLOWED_ORIGINS"]

    # Storage account configuration
    AZURE_ACCOUNT_NAME = os.environ["AZURE_ACCOUNT_NAME"]
    AZURE_STORAGE_KEY = os.environ["AZURE_STORAGE_KEY"]
    AZURE_CUSTOM_DOMAIN = os.environ["AZURE_CUSTOM_DOMAIN"]
    AZURE_MEDIA_CONTAINER = os.environ["AZURE_MEDIA_CONTAINER"]
except KeyError as e:
    missing_variable = e.args[0]
    raise RuntimeError(f"Environment variable {missing_variable} is not set")

DEBUG = False

# Security configuration
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SECURE_REDIRECT_EXEMPT = [
    r"^health/$",
    r"^health$",
    r"^admin/",
    r"^static/",
]

# CSRF configuration
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in csrf_trusted_origins.split(",") if origin.strip()
]

# CORS configuration
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in cors_allowed_origins.split(",") if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOWED_METHODS = [
    "OPTIONS",
    "DELETE",
    "GET",
    "PATCH",
    "POST",
    "PUT",
]


# Media configuration
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = f"https://{AZURE_CUSTOM_DOMAIN}/{AZURE_MEDIA_CONTAINER}/"

STORAGES = {
    "default": {
        "BACKEND": "hotcalls.storage_backends.AzureMediaStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

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
