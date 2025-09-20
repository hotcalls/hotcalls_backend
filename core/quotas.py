from django.db import transaction, models
from django.utils import timezone
from django.core.cache import cache
from decimal import Decimal
import datetime
from typing import Tuple, Optional


class QuotaExceeded(Exception):
    """
    Exception raised when a workspace exceeds its quota for a feature.
    """
    pass


def current_billing_window(subscription) -> Tuple[datetime.datetime, datetime.datetime]:
    """
    Calculate the current billing period start and end dates.
    
    Args:
        subscription: WorkspaceSubscription instance
        
    Returns:
        Tuple of (period_start, period_end) as timezone-aware datetimes
    """
    import calendar
    
    now = timezone.now()
    start_date = subscription.started_at
    
    # Calculate months since subscription start
    months_diff = (now.year - start_date.year) * 12 + (now.month - start_date.month)
    
    # If we haven't reached the billing day this month, go back one month
    if now.day < start_date.day:
        months_diff -= 1
    
    # Calculate current period start year and month
    period_year = start_date.year + (start_date.month - 1 + months_diff) // 12
    period_month = ((start_date.month - 1 + months_diff) % 12) + 1
    
    # Handle day overflow (e.g., Jan 31 -> Feb 28/29)
    max_day_in_month = calendar.monthrange(period_year, period_month)[1]
    period_day = min(start_date.day, max_day_in_month)
    
    period_start = start_date.replace(
        year=period_year,
        month=period_month,
        day=period_day
    )
    
    # Calculate next period start (which becomes period end)
    if period_month == 12:
        next_period_year = period_year + 1
        next_period_month = 1
    else:
        next_period_year = period_year
        next_period_month = period_month + 1
    
    # Handle day overflow for next period
    max_day_in_next_month = calendar.monthrange(next_period_year, next_period_month)[1]
    next_period_day = min(start_date.day, max_day_in_next_month)
    
    period_end = start_date.replace(
        year=next_period_year,
        month=next_period_month,
        day=next_period_day
    )
    
    return period_start, period_end


def initialize_feature_usage_for_subscription(subscription):
    """
    Create FeatureUsage records for all features in the plan
    for the current billing period (eager initialization).

    Uses workspace+period as key, not subscription, to avoid duplicates
    when subscriptions change.

    Args:
        subscription: WorkspaceSubscription instance

    Returns:
        WorkspaceUsage instance for current billing period
    """
    from core.models import WorkspaceUsage, FeatureUsage, PlanFeature
    from decimal import Decimal

    # Get current billing period
    period_start, period_end = current_billing_window(subscription)

    # Get or create WorkspaceUsage container (ONE per workspace+period)
    usage_container, created = WorkspaceUsage.objects.get_or_create(
        workspace=subscription.workspace,
        period_start=period_start,
        period_end=period_end,
        defaults={'subscription': subscription}
    )

    # If container exists but has different subscription, update it to current active subscription
    if not created and usage_container.subscription != subscription:
        usage_container.subscription = subscription
        usage_container.save(update_fields=['subscription'])

    # Create FeatureUsage records for all features in the plan (IDEMPOTENT)
    plan_features = PlanFeature.objects.filter(plan=subscription.plan).select_related('feature')

    # Get existing feature IDs to avoid duplicates
    existing_feature_ids = set(
        usage_container.feature_usages.values_list('feature_id', flat=True)
    )

    for plan_feature in plan_features:
        if plan_feature.feature_id not in existing_feature_ids:
            # Calculate initial usage based on feature type
            initial_usage = Decimal('0')

            # For capacity limits, count existing entities
            if plan_feature.feature.feature_name == 'max_agents':
                from core.models import Agent
                agent_count = Agent.objects.filter(workspace=subscription.workspace).count()
                initial_usage = Decimal(str(agent_count))
            elif plan_feature.feature.feature_name == 'max_users':
                user_count = subscription.workspace.users.count()
                initial_usage = Decimal(str(user_count))
            # For consumption features (call_minutes, etc.), start at 0

            FeatureUsage.objects.create(
                usage_record=usage_container,
                feature=plan_feature.feature,
                used_amount=initial_usage
            )

    return usage_container


def ensure_current_period_initialized(subscription):
    """
    Ensure current billing period has all FeatureUsage records.
    Handles billing period transitions automatically and prevents duplicates.

    Args:
        subscription: WorkspaceSubscription instance

    Returns:
        WorkspaceUsage instance for current billing period
    """
    from core.models import WorkspaceUsage

    period_start, period_end = current_billing_window(subscription)

    # Check if current period container exists (search by workspace+period, not subscription)
    usage_container = WorkspaceUsage.objects.filter(
        workspace=subscription.workspace,
        period_start=period_start,
        period_end=period_end,
    ).first()

    if not usage_container:
        # New billing period - create container and all feature records
        usage_container = initialize_feature_usage_for_subscription(subscription)
    else:
        # Update existing container to point to current active subscription
        if usage_container.subscription != subscription:
            usage_container.subscription = subscription
            usage_container.save(update_fields=['subscription'])

    return usage_container


def get_usage_container(workspace):
    """
    Get or create the WorkspaceUsage container for the current billing period.
    Now includes eager FeatureUsage initialization and prevents duplicates.

    Args:
        workspace: Workspace instance

    Returns:
        WorkspaceUsage instance for current billing period

    Raises:
        WorkspaceSubscription.DoesNotExist: If no active subscription found
    """
    from core.models import WorkspaceSubscription, WorkspaceUsage

    # Get active subscription
    subscription = WorkspaceSubscription.objects.select_related("plan").get(
        workspace=workspace,
        is_active=True
    )

    # Calculate current billing window
    period_start, period_end = current_billing_window(subscription)

    # Get or create usage container (ONE per workspace+period)
    usage_container, created = WorkspaceUsage.objects.get_or_create(
        workspace=workspace,
        period_start=period_start,
        period_end=period_end,
        defaults={'subscription': subscription}
    )

    # If container exists but has different subscription, update it to current active subscription
    if not created and usage_container.subscription != subscription:
        usage_container.subscription = subscription
        usage_container.save(update_fields=['subscription'])

    # Ensure FeatureUsage records are initialized (IDEMPOTENT)
    from core.models import FeatureUsage, PlanFeature
    from decimal import Decimal

    plan_features = PlanFeature.objects.filter(plan=subscription.plan).select_related('feature')

    # Get existing feature IDs to avoid duplicates
    existing_feature_ids = set(
        usage_container.feature_usages.values_list('feature_id', flat=True)
    )

    for plan_feature in plan_features:
        if plan_feature.feature_id not in existing_feature_ids:
            FeatureUsage.objects.create(
                usage_record=usage_container,
                feature=plan_feature.feature,
                used_amount=Decimal('0')
            )

    return usage_container


def enforce_and_record(
    *,
    workspace,
    route_name: str,
    http_method: str = "POST",
    amount: int | float = 1,
) -> None:
    """
    Enforce quota limits and record usage for a given route/operation.
    
    This function works for both real HTTP routes and virtual routes:
    • Real routes: from Django middleware using request.resolver_match.view_name
    • Virtual routes: from workers/webhooks using custom route names
    
    Args:
        workspace: Workspace instance
        route_name: Route identifier (Django route name or virtual route)
        http_method: HTTP method or operation type 
        amount: Usage amount to record (default: 1)
        
    Raises:
        QuotaExceeded: If the operation would exceed the workspace's quota
        
    Examples:
        # Real HTTP route (called from middleware)
        enforce_and_record(
            workspace=request.user.workspace,
            route_name="agent_api:agent-list", 
            http_method="POST",
            amount=1
        )
        
        # Virtual route (called from worker/webhook)
        enforce_and_record(
            workspace=workspace,
            route_name="internal:some_operation",
            http_method="POST", 
            amount=5
        )
    """
    # Convert to Decimal and validate
    amount = Decimal(str(amount))
    if amount < 0:
        raise ValueError(f"Usage amount must be positive, got {amount}")
    
    from core.models import EndpointFeature, FeatureUsage
    
    # Look up route mapping in EndpointFeature
    mapping = EndpointFeature.objects.select_related("feature").filter(
        route_name=route_name,
        http_method=http_method,
    ).first()
    
    if not mapping:
        # Route is not metered → free operation
        return
    
    feature = mapping.feature
    
    with transaction.atomic():
        # Get usage container for current billing period
        usage_container = get_usage_container(workspace)
        
        # Get or create feature usage record
        feature_usage, created = FeatureUsage.objects.select_for_update().get_or_create(
            usage_record=usage_container,
            feature=feature,
            defaults={"used_amount": Decimal('0')},
        )
        
        # Get limit from plan (may be None for unlimited)
        limit = feature_usage.limit
        effective_limit = limit
        
        # SPECIAL CASE: For capacity limits (max_users, max_agents), check actual entity count
        if feature.feature_name == 'max_agents':
            from core.models import Agent
            current_count = Agent.objects.filter(workspace=workspace).count()
            new_value = current_count + amount
        elif feature.feature_name == 'max_users':
            current_count = workspace.users.count()
            new_value = current_count + amount
        else:
            # For consumption limits (call_minutes), use quota tracking
            # Include any extra minutes purchased for this billing period
            # effective_limit = plan limit + usage_container.extra_call_minutes (if exists)
            if feature.feature_name == 'call_minutes':
                # Some deployments may not yet have the field; guard access
                extra = getattr(usage_container, 'extra_call_minutes', None)
                if extra is not None and effective_limit is not None:
                    effective_limit = effective_limit + Decimal(str(extra))
            new_value = feature_usage.used_amount + amount
        
        # Check quota
        # Compare against effective limit (plan + extras)
        if effective_limit is not None and new_value > effective_limit:
            raise QuotaExceeded(
                f"{feature.feature_name}: {new_value} exceeds plan limit {effective_limit}"
            )
        
        # Record usage atomically (only for consumption-based features, not capacity limits)
        if feature.feature_name not in ['max_agents', 'max_users']:
            feature_usage.used_amount = models.F("used_amount") + amount
            feature_usage.save(update_fields=["used_amount"])


def get_feature_usage_status(workspace, feature_name: str) -> dict:
    """
    Get current usage status for a specific feature.
    
    Args:
        workspace: Workspace instance
        feature_name: Name of the feature to check
        
    Returns:
        Dict with usage information:
        {
            'used': Decimal,
            'limit': Decimal|None, 
            'remaining': Decimal|None,
            'unlimited': bool
        }
    """
    from core.models import Feature, FeatureUsage
    
    try:
        feature = Feature.objects.get(feature_name=feature_name)
        usage_container = get_usage_container(workspace)
        
        feature_usage = FeatureUsage.objects.filter(
            usage_record=usage_container,
            feature=feature
        ).first()
        
        if not feature_usage:
            # No usage recorded yet
            used = Decimal('0')
        else:
            used = feature_usage.used_amount
            
        # Get limit from plan
        limit = None
        if feature_usage:
            limit = feature_usage.limit
            
        remaining = None
        unlimited = limit is None
        
        if not unlimited:
            remaining = max(limit - used, Decimal('0'))
            
        return {
            'used': used,
            'limit': limit,
            'remaining': remaining, 
            'unlimited': unlimited
        }
        
    except Feature.DoesNotExist:
        return {
            'used': Decimal('0'),
            'limit': None,
            'remaining': None,
            'unlimited': True
        }


# Cache invalidation helpers
def invalidate_endpoint_cache(route_name: str, http_method: str = None):
    """
    Invalidate cache for specific endpoint feature mappings.
    
    Args:
        route_name: Route name to invalidate
        http_method: Specific method to invalidate, or None for all methods
    """
    if http_method:
        cache_key = f"endpoint_feature:{http_method}:{route_name}"
        cache.delete(cache_key)
    else:
        # Invalidate all methods for this route
        from core.models import HTTPMethod
        for method_choice in HTTPMethod.choices:
            method = method_choice[0]
            cache_key = f"endpoint_feature:{method}:{route_name}"
            cache.delete(cache_key)


"""
=== VIRTUAL ROUTE ENFORCEMENT PATTERN ===

For operations that are not HTTP requests (Celery tasks, webhooks, internal services),
use the same quota enforcement pattern by calling enforce_and_record() directly.

IMPLEMENTATION GUIDE FOR FUTURE VIRTUAL ROUTES:

1. Define virtual route naming convention:
   - Use namespace prefixes: "internal:", "webhook:", "worker:"
   - Examples: "internal:call_dnd_bypass", "webhook:meta_leadgen", "worker:ai_analysis"

2. Create EndpointFeature entries in database:
   - route_name: your virtual route name (e.g., "internal:operation_name")
   - http_method: typically "POST" for virtual operations
   - feature: link to the Feature this operation consumes

3. In your worker/webhook/service code:

   ```python
   from core.quotas import enforce_and_record, QuotaExceeded
   
   def some_internal_operation(workspace, data):
       try:
           # Enforce quota before performing operation
           enforce_and_record(
               workspace=workspace,
               route_name="internal:operation_name",
               http_method="POST",
               amount=1  # or calculate based on operation complexity
           )
       except QuotaExceeded as e:
           # Handle quota exceeded - log, notify, queue for later, etc.
           logger.warning(f"Quota exceeded for {workspace}: {e}")
           return {"error": "quota_exceeded", "message": str(e)}
       
       # Proceed with actual operation
       result = perform_operation(data)
       return result
   ```

4. Variable usage amounts:
   - Simple operations: amount=1
   - Time-based: amount=duration_minutes  
   - Data-based: amount=file_size_gb
   - Calculated: amount=complexity_score

5. Common virtual route patterns:
   - Background jobs: "worker:job_type"
   - Webhook processing: "webhook:provider_event"
   - Internal APIs: "internal:service_operation"  
   - Scheduled tasks: "cron:task_name"
   - AI operations: "ai:model_inference"

6. Administration:
   - Virtual routes appear in admin alongside real routes
   - Same quota management - assign to features, set plan limits
   - Monitor usage through existing FeatureUsage reporting

7. Testing virtual routes:
   ```python
   # In tests
   enforce_and_record(
       workspace=test_workspace,
       route_name="test:mock_operation", 
       amount=1
   )
   ```

This pattern provides unified quota enforcement across all workspace operations,
whether triggered by HTTP requests or internal processes.
"""


def get_feature_usage_status_readonly(workspace, feature_name: str) -> dict:
    """
    Get current usage status for a specific feature (read-only version for API endpoints).
    
    This version doesn't use select_for_update, making it safe for read-only operations
    outside of transactions.
    
    Args:
        workspace: Workspace instance
        feature_name: Name of the feature to check
        
    Returns:
        Dict with usage information:
        {
            'used': Decimal,
            'limit': Decimal|None, 
            'remaining': Decimal|None,
            'unlimited': bool
        }
    """
    from core.models import Feature, FeatureUsage, WorkspaceSubscription, WorkspaceUsage
    
    try:
        feature = Feature.objects.get(feature_name=feature_name)
        
        # Get active subscription (read-only)
        subscription = WorkspaceSubscription.objects.select_related("plan").get(
            workspace=workspace, 
            is_active=True
        )
        
        # Calculate current billing window
        period_start, period_end = current_billing_window(subscription)
        
        # Get usage container for this period (read-only)
        usage_container = WorkspaceUsage.objects.filter(
            workspace=workspace,
            subscription=subscription,
            period_start=period_start,
            period_end=period_end,
        ).first()
        
        # SPECIAL CASE: For capacity limits (max_users, max_agents), count actual entities
        if feature.feature_name == 'max_agents':
            from core.models import Agent
            used = Decimal(str(Agent.objects.filter(workspace=workspace).count()))
        elif feature.feature_name == 'max_users':
            used = Decimal(str(workspace.users.count()))
        else:
            # For consumption limits (call_minutes), use quota tracking
            if not usage_container:
                # No usage recorded yet for this period
                used = Decimal('0')
            else:
                # Get feature usage
                feature_usage = FeatureUsage.objects.filter(
                    usage_record=usage_container,
                    feature=feature
                ).first()
                
                if not feature_usage:
                    used = Decimal('0')
                else:
                    used = feature_usage.used_amount
                
        # FIXED: Always get limit from PlanFeature, not from FeatureUsage
        from core.models import PlanFeature
        try:
            plan_feature = PlanFeature.objects.get(
                plan=subscription.plan,
                feature=feature
            )
            limit = plan_feature.limit
        except PlanFeature.DoesNotExist:
            limit = None
            
        # For call_minutes include extra purchased minutes for this period
        effective_limit = limit
        if feature.feature_name == 'call_minutes' and usage_container is not None and limit is not None:
            extra = getattr(usage_container, 'extra_call_minutes', None)
            if extra is not None:
                effective_limit = effective_limit + Decimal(str(extra))
        
        remaining = None
        unlimited = effective_limit is None
        
        if not unlimited:
            remaining = max(effective_limit - used, Decimal('0'))
            
        return {
            'used': used,
            'limit': effective_limit,
            'remaining': remaining, 
            'unlimited': unlimited
        }
        
    except (Feature.DoesNotExist, WorkspaceSubscription.DoesNotExist):
        return {
            'used': Decimal('0'),
            'limit': None,
            'remaining': None,
            'unlimited': True
        }