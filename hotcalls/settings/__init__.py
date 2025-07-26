"""
Django settings package for HotCalls.

This package provides environment-specific settings configurations:
- base.py: Common settings shared across all environments
- development.py: Local development settings
- production.py: Production settings for Azure deployment
- testing.py: Settings optimized for testing

Usage:
    Set DJANGO_SETTINGS_MODULE environment variable to specify which settings to use:
    - development: hotcalls.settings.development
    - production: hotcalls.settings.production
    - testing: hotcalls.settings.testing
"""

import os

# Determine which settings to use based on environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

if ENVIRONMENT == 'production':
    from .production import *
elif ENVIRONMENT == 'testing':
    from .testing import *
else:
    from .development import * 