"""
Storage SDK – vendor‑agnostic cloud storage interface.
"""

from .interface import (
    ConfigurationError,
    DeleteFailedError,
    DownloadFailedError,
    ListError,
    ObjectNotFoundError,
    StorageError,
    StorageProvider,
    StoredObject,
    UploadFailedError,
)
from .factory import get_provider, register_provider
from .async_adapter import AsyncStorageProvider

__all__ = [
    "StorageProvider",
    "StoredObject",
    "StorageError",
    "ObjectNotFoundError",
    "UploadFailedError",
    "DownloadFailedError",
    "DeleteFailedError",
    "ListError",
    "ConfigurationError",
    "get_provider",
    "register_provider",
    "AsyncStorageProvider",
]
