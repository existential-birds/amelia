"""Retry utility with exponential backoff and jitter for transient API failures."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from loguru import logger

from amelia.core.types import RetryConfig


async def with_retry[T](
    fn: Callable[[], Awaitable[T]],
    config: RetryConfig | None = None,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Execute an async callable with retry logic using exponential backoff and jitter.

    Args:
        fn: Async callable (zero-argument) to execute.
        config: Retry configuration. Uses defaults if None.
        retryable_exceptions: Exception types that should trigger a retry.
            Non-matching exceptions propagate immediately.

    Returns:
        The return value of the callable on success.

    Raises:
        The last exception encountered if all retries are exhausted,
        or any non-retryable exception immediately.
    """
    if config is None:
        config = RetryConfig()

    last_exception: BaseException | None = None

    for attempt in range(1 + config.max_retries):
        try:
            return await fn()
        except BaseException as exc:
            if not isinstance(exc, retryable_exceptions):
                raise

            last_exception = exc

            if attempt >= config.max_retries:
                raise

            delay = config.base_delay * (2**attempt)
            jitter = random.uniform(0, 0.25 * delay)  # noqa: S311
            delay = min(delay + jitter, config.max_delay)

            logger.warning(
                "Retrying after error",
                attempt=attempt + 1,
                delay=round(delay, 3),
                error=str(exc),
            )

            await asyncio.sleep(delay)

    # This should be unreachable, but satisfies the type checker.
    assert last_exception is not None  # noqa: S101
    raise last_exception
