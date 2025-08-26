#!/usr/bin/env python
"""Test Azure storage configuration in Django"""

from django.conf import settings
import os

print("=" * 60)
print("AZURE STORAGE CONFIGURATION CHECK")
print("=" * 60)

# Check environment
print(f"Environment: {os.environ.get('ENVIRONMENT', 'Not set')}")
print(f"Django Settings Module: {os.environ.get('DJANGO_SETTINGS_MODULE', 'Not set')}")
print("")

# Check Azure credentials
print("Azure Credentials:")
print(f"  AZURE_ACCOUNT_NAME: {getattr(settings, 'AZURE_ACCOUNT_NAME', 'NOT SET')}")
print(f"  AZURE_STORAGE_KEY exists: {bool(getattr(settings, 'AZURE_STORAGE_KEY', None))}")
print(f"  AZURE_MEDIA_CONTAINER: {getattr(settings, 'AZURE_MEDIA_CONTAINER', 'NOT SET')}")
print(f"  AZURE_STATIC_CONTAINER: {getattr(settings, 'AZURE_STATIC_CONTAINER', 'NOT SET')}")
print("")

# Check storage backends
print("Storage Backends:")
print(f"  DEFAULT_FILE_STORAGE: {getattr(settings, 'DEFAULT_FILE_STORAGE', 'NOT SET')}")
print(f"  MEDIA_URL: {settings.MEDIA_URL}")
print(f"  MEDIA_ROOT: {getattr(settings, 'MEDIA_ROOT', 'NOT SET')}")

# Check Django 4.2+ STORAGES setting
if hasattr(settings, 'STORAGES'):
    print(f"  STORAGES (Django 4.2+): {list(settings.STORAGES.keys())}")
    if 'default' in settings.STORAGES:
        print(f"    Default backend: {settings.STORAGES['default'].get('BACKEND', 'NOT SET')}")
print("")

# Try to initialize the storage backend
print("Testing Storage Backend Initialization:")
try:
    from django.core.files.storage import default_storage
    print(f"  Storage class: {default_storage.__class__.__name__}")
    print(f"  Storage module: {default_storage.__class__.__module__}")
    
    # Check if it's Azure storage
    if hasattr(default_storage, 'account_name'):
        print(f"  Azure Account: {default_storage.account_name}")
        print(f"  Azure Container: {default_storage.azure_container}")
        print("  ✅ Azure Storage is configured!")
    else:
        print("  ⚠️ Not using Azure Storage - using local storage")
        
except Exception as e:
    print(f"  ❌ Error initializing storage: {e}")

print("=" * 60)
