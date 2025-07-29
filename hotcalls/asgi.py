"""
ASGI config for hotcalls project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

# Set default settings module based on environment
environment = os.environ.get('ENVIRONMENT', 'development')
default_settings = f'hotcalls.settings.{environment}'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', default_settings)

application = get_asgi_application()
