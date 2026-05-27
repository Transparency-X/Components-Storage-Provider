"""
Async wrapper that runs synchronous StorageProvider methods in a thread pool,
making them safe for asyncio applications.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, BinaryIO, Optional

from .interface import StorageProvider, StoredObject

# Default shared executor can be customised.
_default_executor = ThreadPoolExecutor(max_workers=10)


class AsyncStorageProvider:
    """
    Wraps a synchronous `StorageProvider` and exposes the same operations as
    coroutines.
    
    Example::
    
        async_store = AsyncStorageProvider(sync_store)
        obj = await async_store.upload_fileobj(key, data)
    """

    def __init__(
        self,
        sync_provider: StorageProvider,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        self._sync = sync_provider
        self._executor = executor or _default_executor

    async def upload_fileobj(
        self,
        key: str,
        data: BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        return await self._run_in_thread(
            self._sync.upload_fileobj, key, data, content_type
        )

    async def download_fileobj(self, key: str, target: BinaryIO) -> StoredObject:
        return await self._run_in_thread(
            self._sync.download_fileobj, key, target
        )

    async def download_bytes(self, key: str) -> bytes:
        return await self._run_in_thread(self._sync.download_bytes, key)

    async def delete(self, key: str) -> None:
        return await self._run_in_thread(self._sync.delete, key)

    async def list_objects(
        self, prefix: str = "", *, max_keys: int = 1000
    ) -> AsyncIterator[StoredObject]:
        """
        Collect all results from the synchronous iterator in a thread and yield
        them one by one. For very large result sets consider a streaming
        implementation in the future.
        """
        def _sync_list():
            return list(self._sync.list_objects(prefix, max_keys=max_keys))

        results = await self._run_in_thread(_sync_list)
        for obj in results:
            yield obj

    async def exists(self, key: str) -> bool:
        return await self._run_in_thread(self._sync.exists, key)

    async def head(self, key: str) -> StoredObject:
        return await self._run_in_thread(self._sync.head, key)

    async def presigned_url(self, key: str, expiration: int = 3600) -> str:
        return await self._run_in_thread(self._sync.presigned_url, key, expiration)

    async def _run_in_thread(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )
