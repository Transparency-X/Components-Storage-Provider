"""
Cross‑cutting decorators for logging, retry, and (future) metrics.
"""

import functools
import logging
import time
from typing import Callable, TypeVar

from botocore.exceptions import ClientError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .interface import StorageError

F = TypeVar("F", bound=Callable)

logger = logging.getLogger(__name__)


def log_operation(func: F) -> F:
    """Log every storage operation with timing and status."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        start = time.monotonic()
        try:
            result = func(self, *args, **kwargs)
            elapsed = time.monotonic() - start
            logger.info(
                "%s.%s completed in %.3fs",
                type(self).__name__,
                func.__name__,
                elapsed,
            )
            return result
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "%s.%s failed after %.3fs: %s",
                type(self).__name__,
                func.__name__,
                elapsed,
                exc,
            )
            raise

    return wrapper  # type: ignore[return-value]


def retry_on_transient_error(func: F) -> F:
    """
    Retry on network/transient boto3 ClientErrors.
    Does *not* retry on 4xx (except 429) or on our own `StorageError`.
    """
    retry_decorator = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ClientError),
        reraise=True,
    )
    return retry_decorator(func)  # type: ignore[return-value]
