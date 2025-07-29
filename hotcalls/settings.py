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
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-=a8o!^u&0e(!-p_$f)ppq2r=*)$g8v(3lrb*vl@+b%i!pn8-=r"
)
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

TIME_ZONE = os.environ.get("TIME_ZONE", "Europe/Berlin")
USE_TZ = True

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "False").lower() == "true"
SESSION_COOKIE_SECURE = (
    os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
)
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "False").lower() == "true"
SECURE_BROWSER_XSS_FILTER = (
    os.environ.get("SECURE_BROWSER_XSS_FILTER", "False").lower() == "true"
)
SECURE_CONTENT_TYPE_NOSNIFF = (
    os.environ.get("SECURE_CONTENT_TYPE_NOSNIFF", "False").lower() == "true"
)
X_FRAME_OPTIONS = os.environ.get("X_FRAME_OPTIONS", "DENY")

STATIC_URL = os.environ.get("STATIC_URL", "static/")
STATIC_ROOT = BASE_DIR / "staticfiles"
ROOT_URLCONF = "hotcalls.urls"

# Custom User Model
AUTH_USER_MODEL = 'core.User'

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "core",
    "django_celery_beat",
    "drf_yasg",
    # Additional DRF packages
    'drf_spectacular',
    'django_filters',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.DisableCSRFForPaymentAPI",  # Disable CSRF for payment API
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = (
    os.environ.get("CORS_ALLOW_ALL_ORIGINS", "True").lower() == "true"
)


DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
        'NAME': os.environ.get('DB_NAME', 'hotcalls_db'),
        'USER': os.environ.get('DB_USER', 'hotcalls_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

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

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# Spectacular (Swagger) Settings
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

### 👤 User Management API (`/api/users/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Users** | ✅ Own profile only | ✅ All users | ✅ All users | Users filtered by ownership |
| **Create User** | ✅ Public registration | ✅ Any user | ✅ Any user | No authentication required |
| **Edit User** | ✅ Own profile only | ✅ Any user | ✅ Any user | Object-level permission check |
| **Delete User** | ❌ No access | ❌ No access | ✅ Any user | Destructive operation restricted |
| **Change Status** | ❌ No access | ✅ Any user | ✅ Any user | Staff can activate/deactivate |
| **View Blacklist** | ❌ No access | ✅ All entries | ✅ All entries | Staff-only security feature |
| **Manage Blacklist** | ❌ No access | ✅ Create/Edit | ✅ All operations | High-security operations |

### 📋 Subscription Management API (`/api/subscriptions/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Plans** | ✅ All plans | ✅ All plans | ✅ All plans | Public information |
| **View Features** | ✅ All features | ✅ All features | ✅ All features | Public information |
| **Create Plans/Features** | ❌ No access | ✅ Full access | ✅ Full access | Business configuration |
| **Edit Plans/Features** | ❌ No access | ✅ Full access | ✅ Full access | Business configuration |
| **Delete Plans/Features** | ❌ No access | ❌ No access | ✅ Full access | Destructive operations |
| **Manage Assignments** | ❌ No access | ✅ Full access | ✅ Full access | Plan-feature relationships |

### 🏢 Workspace Management API (`/api/workspaces/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Workspaces** | ✅ Own workspaces | ✅ All workspaces | ✅ All workspaces | Filtered by membership |
| **Create Workspace** | ❌ No access | ✅ Full access | ✅ Full access | Organization structure |
| **Edit Workspace** | ❌ No access | ✅ Full access | ✅ Full access | Organization structure |
| **Delete Workspace** | ❌ No access | ❌ No access | ✅ Full access | Destructive operations |
| **Manage Members** | ❌ No access | ✅ Full access | ✅ Full access | User-workspace relationships |
| **View Statistics** | ✅ Own workspaces | ✅ All workspaces | ✅ All workspaces | Analytics access |

### 🤖 Agent Management API (`/api/agents/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Agents** | ✅ Workspace agents | ✅ All agents | ✅ All agents | Filtered by workspace |
| **Create Agent** | ❌ No access | ✅ Full access | ✅ Full access | AI agent configuration |
| **Edit Agent** | ❌ No access | ✅ Full access | ✅ Full access | AI agent configuration |
| **Delete Agent** | ❌ No access | ❌ No access | ✅ Full access | Destructive operations |
| **View Phone Numbers** | ✅ All numbers | ✅ All numbers | ✅ All numbers | System resources |
| **Manage Phone Numbers** | ❌ No access | ✅ Full access | ✅ Full access | System resources |
| **Agent-Phone Assignment** | ❌ No access | ✅ Full access | ✅ Full access | Resource allocation |

### 📞 Lead Management API (`/api/leads/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Leads** | ✅ All leads | ✅ All leads | ✅ All leads | Customer data access |
| **Create Lead** | ✅ Single/Bulk | ✅ Single/Bulk | ✅ Single/Bulk | Data entry operations |
| **Edit Lead** | ❌ No access | ✅ All leads | ✅ All leads | Data modification |
| **Delete Lead** | ❌ No access | ✅ All leads | ✅ All leads | Customer data deletion |
| **Update Metadata** | ❌ No access | ✅ All leads | ✅ All leads | Custom field management |
| **View Call History** | ✅ All leads | ✅ All leads | ✅ All leads | Historical data |

### 📱 Call Management API (`/api/calls/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Call Logs** | ✅ All logs | ✅ All logs | ✅ All logs | Historical call data |
| **Create Call Log** | ❌ No access | ✅ Full access | ✅ Full access | System generated data |
| **Edit Call Log** | ❌ No access | ✅ Full access | ✅ Full access | Data correction |
| **Delete Call Log** | ❌ No access | ❌ No access | ✅ Full access | Destructive operations |
| **View Analytics** | ✅ All analytics | ✅ All analytics | ✅ All analytics | Business intelligence |
| **Daily Statistics** | ✅ All stats | ✅ All stats | ✅ All stats | Reporting access |

### 📅 Calendar Management API (`/api/calendars/`)
| Operation | Regular User | Staff | Superuser | Notes |
|-----------|--------------|-------|-----------|-------|
| **View Calendars** | ✅ Workspace calendars | ✅ All calendars | ✅ All calendars | Filtered by workspace |
| **Create Calendar** | ❌ No access | ✅ Full access | ✅ Full access | Integration setup |
| **Edit Calendar** | ❌ No access | ✅ Full access | ✅ Full access | Integration management |
| **Delete Calendar** | ❌ No access | ❌ No access | ✅ Full access | Destructive operations |
| **View Configurations** | ✅ Workspace configs | ✅ All configs | ✅ All configs | Filtered by workspace |
| **Manage Configurations** | ❌ No access | ✅ Full access | ✅ Full access | Scheduling setup |
| **Check Availability** | ✅ Workspace calendars | ✅ All calendars | ✅ All calendars | Booking operations |

---

## 🚨 Common Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```
**Cause**: No authentication provided or session expired

### 403 Forbidden  
```json
{
  "detail": "You do not have permission to perform this action."
}
```
**Cause**: Insufficient permission level for the operation

### 404 Not Found (Permission-related)
```json
{
  "detail": "Not found."
}
```
**Cause**: Resource exists but user lacks permission to view it

---

## 📚 Getting Started

1. **Authenticate**: Use the "Authorize" button below to login
2. **Test Permissions**: Try different endpoints based on your role
3. **Check Responses**: See how permissions filter your results
4. **Handle Errors**: Implement proper error handling for 401/403 responses

**Legend**: ✅ = Allowed, ❌ = Forbidden
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

# CORS Settings (for frontend development)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React development server
    "http://127.0.0.1:3000",
    "http://localhost:8080",  # Vue development server
    "http://127.0.0.1:8080",
]

CORS_ALLOW_CREDENTIALS = True

# CSRF Trusted Origins for frontend development
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# Allow CORS headers for CSRF
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
]

# Expose CSRF header to frontend
CORS_EXPOSE_HEADERS = ['X-CSRFToken']


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
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
    },
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

# Google Calendar Integration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = f"{BASE_URL}/api/calendars/google/callback"
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]
