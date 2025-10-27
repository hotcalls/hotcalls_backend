"""
Django settings package for HotCalls.

Contains environment specific configurations, in addition to base configuration
"""

import os

# Determine which settings to use based on environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

if ENVIRONMENT == 'production':
    from .production import *
elif ENVIRONMENT == 'staging':
    from .staging import *
else:
    from .development import *
