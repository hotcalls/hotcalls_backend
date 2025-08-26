"""
Azure Blob Storage backends for Django static and media files.

These storage backends integrate Django with Azure Blob Storage for scalable
file storage in production environments.
"""

import logging
from django.conf import settings
from storages.backends.azure_storage import AzureStorage

logger = logging.getLogger(__name__)


class AzureStaticStorage(AzureStorage):
    """
    Azure Blob Storage backend for Django static files.
    
    This storage backend is used to serve static files (CSS, JS, images)
    from Azure Blob Storage with optional CDN integration.
    """
    account_name = getattr(settings, 'AZURE_ACCOUNT_NAME', None)
    account_key = getattr(settings, 'AZURE_STORAGE_KEY', None)
    azure_container = getattr(settings, 'AZURE_STATIC_CONTAINER', 'static')
    expiration_secs = None
    overwrite_files = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set custom domain for CDN if available
        if hasattr(settings, 'AZURE_CUSTOM_DOMAIN') and settings.AZURE_CUSTOM_DOMAIN:
            self.custom_domain = settings.AZURE_CUSTOM_DOMAIN
        
        # Log configuration for debugging
        logger.info(f"AzureStaticStorage initialized - Account: {self.account_name}, Container: {self.azure_container}")


class AzureMediaStorage(AzureStorage):
    """
    Azure Blob Storage backend for Django media files.
    
    This storage backend is used for user-uploaded files and other
    dynamic media content.
    """
    account_name = getattr(settings, 'AZURE_ACCOUNT_NAME', None)
    account_key = getattr(settings, 'AZURE_STORAGE_KEY', None)
    azure_container = getattr(settings, 'AZURE_MEDIA_CONTAINER', 'media')
    expiration_secs = None
    overwrite_files = False  # Don't overwrite existing media files
    
    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
            # Set custom domain for CDN if available
            if hasattr(settings, 'AZURE_CUSTOM_DOMAIN') and settings.AZURE_CUSTOM_DOMAIN:
                self.custom_domain = settings.AZURE_CUSTOM_DOMAIN
            
            # Log configuration for debugging
            logger.info(f"AzureMediaStorage initialized - Account: {self.account_name}, Container: {self.azure_container}")
        except Exception as e:
            logger.error(f"Failed to initialize AzureMediaStorage: {str(e)}")
            logger.error(f"Azure config - Account: {self.account_name}, Key exists: {bool(self.account_key)}, Container: {self.azure_container}")
            raise