"""
Azure Blob Storage backends for Django static and media files.

These storage backends integrate Django with Azure Blob Storage for scalable
file storage in production environments.
"""

from django.conf import settings
from storages.backends.azure_storage import AzureStorage


class AzureStaticStorage(AzureStorage):
    """
    Azure Blob Storage backend for Django static files.
    
    This storage backend is used to serve static files (CSS, JS, images)
    from Azure Blob Storage with optional CDN integration.
    """
    account_name = settings.AZURE_ACCOUNT_NAME
    account_key = settings.AZURE_STORAGE_KEY
    azure_container = settings.AZURE_STATIC_CONTAINER
    expiration_secs = None
    overwrite_files = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set custom domain for CDN if available
        if hasattr(settings, 'AZURE_CUSTOM_DOMAIN') and settings.AZURE_CUSTOM_DOMAIN:
            self.custom_domain = settings.AZURE_CUSTOM_DOMAIN


class AzureMediaStorage(AzureStorage):
    """
    Azure Blob Storage backend for Django media files.
    
    This storage backend is used for user-uploaded files and other
    dynamic media content.
    """
    account_name = settings.AZURE_ACCOUNT_NAME
    account_key = settings.AZURE_STORAGE_KEY
    azure_container = settings.AZURE_MEDIA_CONTAINER
    expiration_secs = None
    overwrite_files = False  # Don't overwrite existing media files
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set custom domain for CDN if available
        if hasattr(settings, 'AZURE_CUSTOM_DOMAIN') and settings.AZURE_CUSTOM_DOMAIN:
            self.custom_domain = settings.AZURE_CUSTOM_DOMAIN 