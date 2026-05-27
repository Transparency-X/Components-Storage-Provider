"""
Base adapter for S3‑compatible backends. Handles error translation,
pagination, metadata normalisation, and common boto3 interactions.
"""

import datetime
import logging
from typing import BinaryIO, Iterator, Optional

import boto3
from botocore.exceptions import ClientError

from .interface import (
    DeleteFailedError,
    DownloadFailedError,
    ListError,
    ObjectNotFoundError,
    StorageProvider,
    StoredObject,
    UploadFailedError,
)
from .decorators import log_operation, retry_on_transient_error

logger = logging.getLogger(__name__)


class BaseS3Storage(StorageProvider):
    """
    Concrete implementation using an already‑configured boto3 S3 client.
    
    Subclasses (or factory functions) are responsible for creating the client
    with the correct endpoint and credentials.
    """

    def __init__(self, bucket: str, client: "boto3.client") -> None:
        self._bucket = bucket
        self._client = client

    @retry_on_transient_error
    @log_operation
    def upload_fileobj(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        size = None
        # Try to determine size without consuming the stream
        if hasattr(data, "seekable") and data.seekable():
            try:
                pos = data.tell()
                data.seek(0, 2)  # end of stream
                size = data.tell()
                data.seek(pos)  # back to original position
            except (OSError, AttributeError):
                # Some streams may claim seekable but not support full seeking.
                pass

        try:
            self._client.upload_fileobj(
                data,
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        except ClientError as exc:
            raise UploadFailedError(f"Upload of {key} failed: {exc}") from exc

        # Fetch authoritative metadata after upload
        return self.head(key)

    @retry_on_transient_error
    @log_operation
    def download_fileobj(self, key: str, target: BinaryIO) -> StoredObject:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_no_such_key(exc):
                raise ObjectNotFoundError(key) from exc
            raise DownloadFailedError(f"Download of {key} failed: {exc}") from exc

        body = response["Body"]
        # Stream in chunks
        for chunk in body.iter_chunks(chunk_size=8192):
            target.write(chunk)

        return StoredObject(
            key=key,
            size=response["ContentLength"],
            last_modified=response["LastModified"],
            etag=response.get("ETag"),
        )

    @log_operation
    def download_bytes(self, key: str) -> bytes:
        import io

        buf = io.BytesIO()
        self.download_fileobj(key, buf)
        return buf.getvalue()

    @retry_on_transient_error
    @log_operation
    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_no_such_key(exc):
                raise ObjectNotFoundError(key) from exc
            raise DeleteFailedError(f"Deletion of {key} failed: {exc}") from exc

    @log_operation
    def list_objects(self, prefix: str = "", *, max_keys: int = 1000) -> Iterator[StoredObject]:
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=self._bucket,
                Prefix=prefix,
                PaginationConfig={"MaxItems": max_keys, "PageSize": 1000},
            )
            for page in pages:
                for obj in page.get("Contents", []):
                    yield StoredObject(
                        key=obj["Key"],
                        size=obj["Size"],
                        last_modified=obj["LastModified"],
                        etag=obj.get("ETag"),
                    )
        except ClientError as exc:
            raise ListError(f"List objects failed with prefix '{prefix}': {exc}") from exc

    @log_operation
    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if _is_no_such_key(exc):
                return False
            # Re‑raise other errors (auth, network, etc.)
            raise StorageError(f"Unexpected error checking existence of {key}: {exc}") from exc

    @retry_on_transient_error
    @log_operation
    def head(self, key: str) -> StoredObject:
        try:
            meta = self._client.head_object(Bucket=self._bucket, Key=key)
            return StoredObject(
                key=key,
                size=meta["ContentLength"],
                last_modified=meta["LastModified"],
                etag=meta.get("ETag"),
            )
        except ClientError as exc:
            if _is_no_such_key(exc):
                raise ObjectNotFoundError(key) from exc
            raise StorageError(f"HEAD request failed for {key}: {exc}") from exc

    @log_operation
    def presigned_url(self, key: str, expiration: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiration,
        )


def _is_no_such_key(error: ClientError) -> bool:
    """Return True if the error indicates the key does not exist."""
    code = error.response.get("Error", {}).get("Code", "")
    return code in ("NoSuchKey", "404")
