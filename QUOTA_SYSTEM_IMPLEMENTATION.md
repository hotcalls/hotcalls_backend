# Quota System Implementation

## Overview

The quota middleware enforcement pattern has been successfully implemented for your HotCalls project. This system provides unified quota enforcement for both HTTP requests and virtual/internal operations while leveraging your existing usage tracking models.

## Components Implemented

### 1. Core Quota Module (`core/quotas.py`)

**Key Functions:**
- `enforce_and_record()` - Main quota enforcement function for all operations
- `get_usage_container()` - Manages billing period containers
- `current_billing_window()` - Calculates billing periods based on subscription
- `get_feature_usage_status()` - Reports current usage status
- `QuotaExceeded` - Exception raised when quotas are exceeded

**Features:**
- Works with existing `Feature`, `PlanFeature`, `WorkspaceUsage`, `FeatureUsage` models
- Atomic transaction handling for usage recording
- Proper billing period management
- Support for different feature units (minutes, requests, GB, etc.)

### 2. HTTP Quota Middleware (`core/middleware.py`)

**Key Features:**
- `PlanQuotaMiddleware` - Django middleware for HTTP request enforcement
- Automatic route detection using Django's `resolver_match.view_name`
- Caching for `EndpointFeature` lookups (1-minute cache)
- Cache invalidation via Django signals
- Graceful error handling with 403 responses

**Behavior:**
- Only processes authenticated requests
- Skips unmetered routes (no `EndpointFeature` entry)
- Returns JSON error responses when quotas exceeded
- Logs quota violations for monitoring

### 3. Django Settings Integration

The middleware has been added to your Django settings after authentication middleware:
```python
MIDDLEWARE = [
    # ... existing middleware ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.PlanQuotaMiddleware",  # ← Added here
    # ... remaining middleware ...
]
```

### 4. Comprehensive Test Suite (`core/tests/test_quotas.py`)

**Test Coverage:**
- Quota enforcement within limits
- Quota exceeded scenarios  
- Unmetered route handling
- Feature usage status reporting
- Middleware behavior
- Billing window calculations
- Edge cases (month overflow, unlimited features)

## How It Works

### For HTTP Requests (Automatic)

1. User makes HTTP request to your API
2. `PlanQuotaMiddleware` intercepts after authentication
3. Checks if route is in `EndpointFeature` table
4. If metered, calls `enforce_and_record()`
5. If quota exceeded, returns 403 response
6. If within limits, request continues normally

### For Virtual Routes (Manual Integration)

Virtual routes are for non-HTTP operations like:
- Celery background tasks
- Webhook processing
- Internal service calls
- Scheduled operations

**Implementation Pattern:**
```python
from core.quotas import enforce_and_record, QuotaExceeded

def some_internal_operation(workspace, data):
    try:
        # Enforce quota before performing operation
        enforce_and_record(
            workspace=workspace,
            route_name="internal:operation_name",  # Virtual route name
            http_method="POST",
            amount=1  # or calculate based on operation
        )
    except QuotaExceeded as e:
        # Handle quota exceeded - log, queue, notify, etc.
        logger.warning(f"Quota exceeded for {workspace}: {e}")
        return {"error": "quota_exceeded", "message": str(e)}
    
    # Proceed with actual operation
    result = perform_operation(data)
    return result
```

## Database Configuration

### Setting Up Quotas

1. **Create Features:**
   ```python
   # Example: API calls feature
   feature = Feature.objects.create(
       feature_name='API_CALLS',
       description='API endpoint calls',
       unit='general_unit'
   )
   ```

2. **Set Plan Limits:**
   ```python
   # Example: 1000 calls per month on Pro plan
   PlanFeature.objects.create(
       plan=pro_plan,
       feature=feature,
       limit=1000
   )
   ```

3. **Map Routes to Features:**
   ```python
   # HTTP route
   EndpointFeature.objects.create(
       feature=feature,
       route_name='agent_api:agent-list',  # Django route name
       http_method='POST'
   )
   
   # Virtual route
   EndpointFeature.objects.create(
       feature=feature,
       route_name='internal:ai_analysis',  # Virtual route name
       http_method='POST'
   )
   ```

## Virtual Route Naming Conventions

Recommended namespace prefixes:
- `internal:*` - Internal service operations
- `webhook:*` - Webhook processing
- `worker:*` - Background job processing
- `cron:*` - Scheduled tasks
- `ai:*` - AI/ML operations

Examples:
- `internal:call_dnd_bypass`
- `webhook:meta_leadgen`
- `worker:lead_import`
- `ai:voice_synthesis`

## Monitoring and Administration

### Usage Reporting
```python
from core.quotas import get_feature_usage_status

status = get_feature_usage_status(workspace, 'API_CALLS')
# Returns: {'used': 750, 'limit': 1000, 'remaining': 250, 'unlimited': False}
```

### Admin Interface
- Virtual routes appear alongside real routes in Django admin
- Same quota management interface for all route types
- Monitor usage through existing `FeatureUsage` model

## Testing the System

Run the quota system tests:
```bash
python manage.py test core.tests.test_quotas
```

The test suite covers:
- Basic quota enforcement
- Quota exceeded scenarios
- Middleware functionality
- Billing period calculations
- Virtual route patterns

## Security & Performance

**Security:**
- All tokens remain encrypted per your requirements [[memory:4785893]]
- Atomic database operations prevent race conditions
- Graceful error handling prevents information leakage

**Performance:**
- 1-minute caching for `EndpointFeature` lookups
- Efficient database queries with `select_related()` and `select_for_update()`
- Minimal overhead for unmetered routes

## Future Extensibility

The system is designed for easy extension:
- Add new features through admin interface
- Create new virtual route namespaces as needed
- Implement custom usage amounts (time-based, data-based, etc.)
- Add new feature units without code changes

The quota enforcement pattern is now fully integrated with your existing models and ready for both HTTP and virtual route quota management.