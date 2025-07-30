"""
Health check utilities for HotCalls Django application.

This module provides health check endpoints that can be used by Kubernetes
for readiness and liveness probes, as well as load balancers.
"""

import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import connections
from django.core.cache import cache
from django.conf import settings
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
import redis
import time

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Basic health check endpoint.
    
    Returns 200 OK if the application is running.
    This is suitable for Kubernetes liveness probes.
    """
    return JsonResponse({
        'status': 'healthy',
        'timestamp': time.time(),
        'version': getattr(settings, 'API_VERSION', '1.0.0'),
    })


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
@permission_classes([AllowAny])
def readiness_check(request):
    """
    Comprehensive readiness check endpoint.
    
    Checks database connectivity, cache availability, and other dependencies.
    This is suitable for Kubernetes readiness probes.
    """
    checks = {
        'database': False,
        'cache': False,
        'redis': False,
    }
    
    overall_status = 'healthy'
    
    # Check database connectivity
    try:
        db_conn = connections['default']
        # Log database connection details for debugging
        db_settings = db_conn.settings_dict
        logger.info(f"Database connection attempt - Host: {db_settings.get('HOST')}, "
                   f"Port: {db_settings.get('PORT')}, "
                   f"Database: {db_settings.get('NAME')}, "
                   f"User: {db_settings.get('USER')}, "
                   f"SSL Mode: {db_settings.get('OPTIONS', {}).get('sslmode', 'none')}")
        
        db_conn.cursor()
        checks['database'] = True
        logger.debug("Database check passed")
    except Exception as e:
        logger.error(f"Database check failed: {str(e)}")
        logger.error(f"Database configuration: {connections['default'].settings_dict}")
        overall_status = 'unhealthy'
    
    # Check cache availability
    try:
        cache.set('health_check', 'ok', 30)
        cache_value = cache.get('health_check')
        checks['cache'] = cache_value == 'ok'
        if checks['cache']:
            logger.debug("Cache check passed")
        else:
            logger.error("Cache check failed: value mismatch")
            overall_status = 'unhealthy'
    except Exception as e:
        logger.error(f"Cache check failed: {str(e)}")
        overall_status = 'unhealthy'
    
    # Check Redis connectivity (for Celery)
    try:
        redis_client = redis.from_url(settings.CELERY_BROKER_URL)
        redis_client.ping()
        checks['redis'] = True
        logger.debug("Redis check passed")
    except Exception as e:
        logger.error(f"Redis check failed: {str(e)}")
        overall_status = 'unhealthy'
    
    status_code = 200 if overall_status == 'healthy' else 503
    
    return JsonResponse({
        'status': overall_status,
        'timestamp': time.time(),
        'checks': checks,
        'version': getattr(settings, 'API_VERSION', '1.0.0'),
    }, status=status_code)


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
@permission_classes([AllowAny])
def startup_check(request):
    """
    Startup check endpoint.
    
    Performs minimal checks to ensure the application has started properly.
    This can be used for Kubernetes startup probes.
    """
    try:
        # Minimal check - ensure settings are loaded
        secret_key_set = bool(settings.SECRET_KEY)
        
        return JsonResponse({
            'status': 'ready' if secret_key_set else 'not_ready',
            'timestamp': time.time(),
            'checks': {
                'settings_loaded': secret_key_set,
            }
        }, status=200 if secret_key_set else 503)
    except Exception as e:
        logger.error(f"Startup check failed: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'timestamp': time.time(),
            'error': str(e),
        }, status=503) 