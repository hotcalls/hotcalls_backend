from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from core.models import EndpointFeature
from core.quotas import enforce_and_record, QuotaExceeded
import logging

logger = logging.getLogger(__name__)


class PlanQuotaMiddleware(MiddlewareMixin):
    """
    Plan-based quota enforcement middleware for HTTP requests.
    
    • Runs for every HTTP request after authentication
    • Checks if (route_name, method) is listed in EndpointFeature  
    • If found, enforces quota using plan limits
    • If quota exceeded, returns 403 Forbidden response
    • If route not metered, request proceeds untouched
    
    This middleware only handles real HTTP requests. Virtual routes 
    (workers, webhooks, etc.) bypass middleware and call enforce_and_record() directly.
    """

    CACHE_KEY_TEMPLATE = "endpoint_feature:{method}:{route}"
    CACHE_TIMEOUT = 60  # 1 minute cache for endpoint mappings

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Process each view request to enforce quota limits.
        
        Returns:
            None: Allow request to continue
            JsonResponse: Block request with quota exceeded error
        """
        # Skip quota check for unauthenticated requests
        if not request.user.is_authenticated:
            return None

        # Skip quota enforcement for superusers (they have unlimited access)
        if request.user.is_superuser:
            return None

        # Get route information
        if not hasattr(request, 'resolver_match') or not request.resolver_match:
            # No route match, let request continue
            return None
            
        route_name = request.resolver_match.view_name
        method = request.method.upper()

        # Skip if no route name
        if not route_name:
            return None

        # Check if this endpoint is metered (with caching)
        mapping = self._get_endpoint_mapping(route_name, method)
        
        if mapping is None:
            # Endpoint is not metered → allow request
            return None

        # Get workspace for quota enforcement
        workspace = self._get_workspace(request)
        if workspace is None:
            return JsonResponse(
                {"detail": "Workspace not found."}, 
                status=403
            )

        # Enforce quota
        try:
            enforce_and_record(
                workspace=workspace,
                route_name=route_name,
                http_method=method,
                amount=1,  # Default amount for HTTP requests
            )
        except QuotaExceeded as exc:
            logger.warning(
                f"Quota exceeded for workspace {workspace.id} on {route_name} {method}: {exc}"
            )
            return JsonResponse(
                {
                    "detail": str(exc),
                    "error_code": "quota_exceeded"
                }, 
                status=403
            )
        except Exception as exc:
            # Log unexpected errors but don't block the request
            logger.error(
                f"Unexpected error in quota enforcement for {workspace.id}: {exc}",
                exc_info=True
            )
            # Allow request to continue on unexpected errors
            return None

        # Quota check passed, allow request to continue
        return None

    def _get_endpoint_mapping(self, route_name: str, method: str):
        """
        Get EndpointFeature mapping with caching.
        
        Returns:
            EndpointFeature instance or None if not found
        """
        cache_key = self.CACHE_KEY_TEMPLATE.format(method=method, route=route_name)
        mapping = cache.get(cache_key)
        
        if mapping is None:
            # Cache miss - query database
            mapping = (
                EndpointFeature.objects
                .filter(route_name=route_name, http_method=method)
                .select_related("feature")
                .first()
            )
            
            # Cache the result (even if None) to avoid repeated DB queries
            cache.set(cache_key, mapping, timeout=self.CACHE_TIMEOUT)
            
        return mapping

    def _get_workspace(self, request):
        """
        Get workspace for the authenticated user.
        
        Returns:
            Workspace instance or None if not found
        """
        try:
            # Check if user has a direct workspace attribute
            if hasattr(request.user, 'workspace') and request.user.workspace:
                return request.user.workspace
                
            # Fallback: get workspace from user's workspace relationships
            workspaces = request.user.mapping_user_workspaces.all()
            if workspaces.exists():
                # For now, use the first workspace
                # TODO: Handle multiple workspaces based on request context
                return workspaces.first()
                
            return None
            
        except Exception as exc:
            logger.error(f"Error getting workspace for user {request.user.id}: {exc}")
            return None


# Signal handlers for cache invalidation
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender=EndpointFeature)
def invalidate_endpoint_cache_on_save(sender, instance, **kwargs):
    """
    Invalidate cache when EndpointFeature is created or updated.
    """
    from core.quotas import invalidate_endpoint_cache
    invalidate_endpoint_cache(instance.route_name, instance.http_method)


@receiver(post_delete, sender=EndpointFeature)  
def invalidate_endpoint_cache_on_delete(sender, instance, **kwargs):
    """
    Invalidate cache when EndpointFeature is deleted.
    """
    from core.quotas import invalidate_endpoint_cache
    invalidate_endpoint_cache(instance.route_name, instance.http_method)