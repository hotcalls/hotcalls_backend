"""
Azure Blob Storage for Django static and media files.
Defined as django backends, point to azure storage account.
"""

import logging
from django.conf import settings
from storages.backends.azure_storage import AzureStorage

logger = logging.getLogger(__name__)


class AzureStaticStorage(AzureStorage):
    """
    Azure Blob Storage backend for Django static files.

    This storage backend is used to serve static files (CSS, JS, images) from Azure Blob Storage.
    """

    account_name = getattr(settings, "AZURE_ACCOUNT_NAME")
    account_key = getattr(settings, "AZURE_STORAGE_KEY")
    azure_container = "static"
    expiration_secs = None
    overwrite_files = True

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        # Keeping custom_domain for the option to change to a cdn. Currently azure_storage_domain is used as custom domain
        if hasattr(settings, "AZURE_CUSTOM_DOMAIN") and settings.AZURE_CUSTOM_DOMAIN:
            self.custom_domain = settings.AZURE_CUSTOM_DOMAIN

        logger.info(
            f"AzureStaticStorage initialized - Account: {self.account_name}, Container: {self.azure_container}"
        )


class AzureMediaStorage(AzureStorage):
    """
    Azure Blob Storage backend for Django media files.

    This storage backend is used for user-uploaded files and other
    dynamic media content.
    """

    account_name = getattr(settings, "AZURE_ACCOUNT_NAME")
    account_key = getattr(settings, "AZURE_STORAGE_KEY")
    azure_container = "media"
    expiration_secs = None
    overwrite_files = False

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        # Keeping custom_domain for the option to change to a cdn. Currently azure_storage_domain is used as custom domain
        if hasattr(settings, "AZURE_CUSTOM_DOMAIN") and settings.AZURE_CUSTOM_DOMAIN:
            self.custom_domain = settings.AZURE_CUSTOM_DOMAIN

        logger.info(
            f"AzureStaticStorage initialized - Account: {self.account_name}, Container: {self.azure_container}"
        )
