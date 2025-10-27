"""
Context processors for making settings available in templates
"""

from django.conf import settings


def base_url(request):
    """Make BASE_URL available in all templates"""
    return {
        "BASE_URL": getattr(settings, "BASE_URL"),
    }
