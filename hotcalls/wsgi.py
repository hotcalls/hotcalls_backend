"""
WSGI config for hotcalls project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application

# Set default settings module based on environment
environment = os.environ.get('ENVIRONMENT', 'development')
default_settings = f'hotcalls.settings.{environment}'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', default_settings)

application = get_wsgi_application()
