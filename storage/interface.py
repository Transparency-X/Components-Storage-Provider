"""
Core interfaces, data models, and exception hierarchy for the storage component.

All applications depend only on the abstract `StorageProvider` to insulate them
from vendor‑specific details.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Iterator, Optional
import datetime


@dataclass(frozen=True)
class StoredObject:
    """Metadata returned after an operation."""
    key: str
    size: int
    last_modified: Optional[datetime.datetime] = None
    etag: Optional[str] = None


class StorageError(Exception):
    """Base exception for all storage failures."""


class ObjectNotFoundError(StorageError):
    """The requested key does not exist."""


class UploadFailedError(StorageError):
    """An upload operation failed."""


class DownloadFailedError(StorageError):
    """A download operation failed."""


class DeleteFailedError(StorageError):
    """A deletion operation failed."""


class ListError(StorageError):
    """A listing operation failed."""


class ConfigurationError(StorageError):
    """Invalid configuration (e.g., missing credentials)."""


class StorageProvider(ABC):
    """
    Abstract storage backend.
    
    Every method may raise `StorageError` or a more specific subclass.
    """

    @abstractmethod
    def upload_fileobj(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """
        Upload a file‑like object.
        
        The object *must* support `read`. If seekable, the implementation will
        try to determine the size before uploading; otherwise metadata is fetched
        after the upload via a HEAD request.
        """
        ...

    @abstractmethod
    def download_fileobj(self, key: str, target: BinaryIO) -> StoredObject:
        """
        Stream object contents into a writable file‑like object.
        
        Returns the object metadata.
        """
        ...

    @abstractmethod
    def download_bytes(self, key: str) -> bytes:
        """
        Return the entire object as bytes. Use only for objects of known
        small size.
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        Delete an object. Raises `ObjectNotFoundError` if the key does not exist.
        """
        ...

    @abstractmethod
    def list_objects(self, prefix: str = "", *, max_keys: int = 1000) -> Iterator[StoredObject]:
        """
        Generator that yields objects matching the prefix.
        
        Handles pagination transparently. `max_keys` limits the total items
        returned (may be approximate for S3).
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return `True` if the key exists."""
        ...

    @abstractmethod
    def head(self, key: str) -> StoredObject:
        """Retrieve metadata without downloading the object."""
        ...

    @abstractmethod
    def presigned_url(self, key: str, expiration: int = 3600) -> str:
        """
        Generate a time‑limited (in seconds) URL for direct download.
        """
        ...

    def supports(self, operation: str) -> bool:
        """
        Optional capability query.
        
        Default implementation returns `True` if the method exists and is callable.
        """
        return hasattr(self, operation) and callable(getattr(self, operation, None))
