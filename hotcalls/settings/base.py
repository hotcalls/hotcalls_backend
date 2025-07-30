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

# Determine environment - development, staging, or production
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

# Log which settings module is being used
logger.info(f"Loading {__name__} settings module for ENVIRONMENT={ENVIRONMENT}")

# Only load .env file in development environment
# In staging/production, Kubernetes provides all environment variables via secrets
if ENVIRONMENT == 'development':
    try:
        load_dotenv()
        logger.info("Development environment: Loaded .env file")
    except Exception as e:
        logger.warning(f"Failed to load .env file: {str(e)}")
        logger.warning("Continuing with environment variables")
else:
    logger.info(f"{ENVIRONMENT.capitalize()} environment: Using environment variables from Kubernetes secrets, not .env file")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
if ENVIRONMENT != 'development':
    # CRITICAL: No default SECRET_KEY in staging/production!
    try:
        SECRET_KEY = os.environ['SECRET_KEY']
    except KeyError:
        raise RuntimeError(
            f"CRITICAL: SECRET_KEY not set in {ENVIRONMENT} environment!\n"
            "This is a security requirement - set SECRET_KEY in environment variables."
        )
else:
    # Development can use a default key
    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "django-insecure-=a8o!^u&0e(!-p_$f)ppq2r=*)$g8v(3lrb*vl@+b%i!pn8-=r"
    )

# Custom User Model
AUTH_USER_MODEL = 'core.User'

# Authentication backends - Email-based authentication
AUTHENTICATION_BACKENDS = [
    'core.management_api.auth_api.backends.EmailBackend',  # Primary: Email authentication with verification
    'django.contrib.auth.backends.ModelBackend',  # Fallback: Default Django backend
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

# Database configuration - FAIL FAST if not configured!
# In staging/production, these MUST come from environment variables
if ENVIRONMENT != 'development':
    # CRITICAL: No defaults in staging/production - fail if not set!
    try:
        DATABASES = {
            'default': {
                'ENGINE': os.environ['DB_ENGINE'],  # Will raise KeyError if missing
                'NAME': os.environ['DB_NAME'],
                'USER': os.environ['DB_USER'],
                'PASSWORD': os.environ['DB_PASSWORD'],
                'HOST': os.environ['DB_HOST'],  # MUST be set - no localhost fallback!
                'PORT': os.environ.get('DB_PORT', '5432'),
                'OPTIONS': {
                    'sslmode': os.environ.get('DB_SSLMODE', 'require'),
                },
            }
        }
    except KeyError as e:
        raise RuntimeError(
            f"CRITICAL: Missing required database configuration: {e}\n"
            f"Environment: {ENVIRONMENT}\n"
            f"Required variables: DB_ENGINE, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST"
        )
else:
    # Development can have defaults for convenience
    DATABASES = {
        'default': {
            'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': os.environ.get('DB_NAME', 'hotcalls_db'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'OPTIONS': {
                'sslmode': os.environ.get('DB_SSLMODE', 'disable'),
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

# Email Configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@hotcalls.com')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

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
        "rest_framework.authentication.TokenAuthentication",
        # SessionAuthentication removed - no CSRF needed for API endpoints
        # Use TokenAuthentication for all API calls
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
# 🔐 HotCalls API - Email-Based Authentication System

## 🎭 Authentication & Email Verification

### 🚀 New Features
- **📧 Email-based login**: Use email instead of username to login
- **✅ Mandatory email verification**: Users MUST verify email before accessing system
- **🔒 Enhanced security**: Email verification enforced at login
- **📱 Responsive emails**: Beautiful HTML verification emails

### 🔑 Authentication Flow
1. **Registration**: POST to `/api/auth/register/` with email, password, name, phone
2. **Email Verification**: User receives email with verification link
3. **Verify Email**: Click link or use `/api/auth/verify-email/{token}/`
4. **Login**: POST to `/api/auth/login/` with email and password
5. **Access APIs**: Use token authentication for protected endpoints

### 📧 Email Verification Requirements
- **🚫 No login without verification**: Cannot access protected APIs
- **📨 Auto-send verification**: Sent automatically on registration
- **🔄 Resend option**: Use `/api/auth/resend-verification/` if needed
- **⏰ Token expiration**: Verification tokens have security expiration

---

## 🎭 User Roles & Permissions

### User Role Hierarchy
| Role | Level | Description | Email Required |
|------|--------|-------------|----------------|
| **👤 Regular User** | `is_authenticated=True` | Standard user - must verify email | ✅ Required |
| **👔 Staff Member** | `is_staff=True` | System staff - must verify email | ✅ Required |
| **🔧 Superuser** | `is_superuser=True` | Admin - auto-verified | ✅ Auto-verified |

### 🔑 Authentication Methods
- **Token Authentication**: Login via `/api/auth/login/` then use `Authorization: Token <token>`
- **No CSRF Required**: Token authentication doesn't need CSRF tokens
- **⚠️ Email Verification Required**: Must verify email before login

---

## 📊 Complete Permission Matrix

### 🔐 Authentication API (`/api/auth/`)
| Operation | Permission | Email Verification | Description |
|-----------|------------|-------------------|-------------|
| **Register** | Public | Not required | Create account, sends verification email |
| **Verify Email** | Public | Completes verification | Verify email with token from email |
| **Login** | Public | ✅ Required | Login with email/password (verified only) |
| **Logout** | Authenticated | ✅ Required | Clear user session |
| **Profile** | Authenticated | ✅ Required | Get current user profile |
| **Resend Verification** | Public | For unverified emails | Resend verification email |

### 👤 User Management API (`/api/users/`)
| Operation | Regular User | Staff | Superuser | Email Verification |
|-----------|--------------|-------|-----------|-------------------|
| **View Users** | ✅ Own profile | ✅ All users | ✅ All users | ✅ Required |
| **Create User** | ❌ Use auth/register | ✅ Any user | ✅ Any user | ✅ Required |
| **Edit User** | ✅ Own profile | ✅ Any user | ✅ Any user | ✅ Required |
| **Delete User** | ❌ No access | ❌ No access | ✅ Any user | ✅ Required |

### 📋 Other APIs (`/api/subscriptions/`, `/api/workspaces/`, etc.)
- **🔒 All protected APIs require**: Authentication + Email Verification
- **📧 No verification = No access**: Unverified users cannot use any protected endpoints
- **🎯 Same permissions as before**: Role-based access unchanged, just add email verification

---

## 🚨 Authentication Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden - Email Not Verified
```json
{
  "email": ["Please verify your email address before logging in. Check your inbox for the verification email."]
}
```

### 400 Bad Request - Invalid Credentials  
```json
{
  "non_field_errors": ["Unable to log in with provided credentials."]
}
```

### 400 Bad Request - Account Issues
```json
{
  "non_field_errors": ["Your account has been suspended. Please contact support."]
}
```

---

## 📚 Getting Started with Token Authentication

### 1. Register New Account
```bash
POST /api/auth/register/
{
  "email": "user@example.com",
  "password": "securepassword123",
  "password_confirm": "securepassword123",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1234567890"
}
```

### 2. Check Email & Verify
- Check inbox for verification email
- Click verification link or use token

### 3. Login After Verification
```bash
POST /api/auth/login/
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```
Response includes auth token:
```json
{
  "token": "your-auth-token-here",
  "user": {...}
}
```

### 4. Access Protected APIs
```bash
Authorization: Token your-auth-token-here
```

**📧 Remember**: Email verification is mandatory for all users!
    ''',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/',
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': False,
    'TAGS': [
        {'name': 'Authentication', 'description': '🔐 Token-based authentication with mandatory email verification'},
        {'name': 'User Management', 'description': '👤 User accounts and blacklist management - Requires token auth'},
        {'name': 'Subscription Management', 'description': '📋 Plans, features, and subscription management'},
        {'name': 'Workspace Management', 'description': '🏢 Workspace and user association management'},
        {'name': 'Agent Management', 'description': '🤖 AI agents and phone number management'},
        {'name': 'Lead Management', 'description': '📞 Lead management and bulk operations'},
        {'name': 'Call Management', 'description': '📱 Call logs and analytics'},
        {'name': 'Calendar Management', 'description': '📅 Calendar integration and scheduling'},
    ],
    'COMPONENT_SECURITY_SCHEMES': {
        'TokenAuth': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Token-based authentication. Format: `Token <your-token>`'
        }
    },
    'SECURITY': [{'TokenAuth': []}],
}

# Celery Configuration - Dynamically constructed from Redis env vars
if ENVIRONMENT != 'development':
    # CRITICAL: No defaults in staging/production - fail if not set!
    try:
        REDIS_HOST = os.environ['REDIS_HOST']
        REDIS_PASSWORD = os.environ['REDIS_PASSWORD']
    except KeyError as e:
        raise RuntimeError(
            f"CRITICAL: Missing required Redis configuration: {e}\n"
            f"Environment: {ENVIRONMENT}\n"
            f"Required variables: REDIS_HOST, REDIS_PASSWORD"
        )
    REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
    REDIS_DB = os.environ.get("REDIS_DB", "0")
else:
    # Development can have defaults
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

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

# File upload settings
# Maximum size for file uploads via forms (1GB for voice files and images)
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024  # 1GB

# Maximum allowed size for a request body (1GB for voice files and images)
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 1024  # 1GB

# For large files, Django will use temporary files instead of loading into memory
FILE_UPLOAD_TEMP_DIR = None  # Use system default

# Permissions for uploaded files
FILE_UPLOAD_PERMISSIONS = 0o644

# Maximum number of fields in a multipart form (default is 1000)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Meta (Facebook/Instagram) Integration Configuration
META_APP_ID = os.getenv('META_APP_ID', '')
META_APP_SECRET = os.getenv('META_APP_SECRET', '')
META_REDIRECT_URI = os.getenv('META_REDIRECT_URI', '')
META_API_VERSION = os.getenv('META_API_VERSION', 'v18.0')

# LiveKit Configuration
LIVEKIT_HOST = os.getenv('LIVEKIT_HOST', '')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY', '')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET', '')