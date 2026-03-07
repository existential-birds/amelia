"""Tests for amelia.core.retry.with_retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.retry import with_retry
from amelia.core.types import RetryConfig


async def test_successful_call_returns_immediately() -> None:
    """A successful call should return its value without any retry."""
    fn = AsyncMock(return_value=42)

    result = await with_retry(fn, RetryConfig(max_retries=3))

    assert result == 42
    fn.assert_awaited_once()


async def test_retries_on_retryable_exception_then_succeeds() -> None:
    """Should retry on a retryable exception and return on the next success."""
    fn = AsyncMock(side_effect=[ValueError("transient"), "ok"])

    with patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await with_retry(
            fn,
            RetryConfig(max_retries=3, base_delay=1.0),
            retryable_exceptions=(ValueError,),
        )

    assert result == "ok"
    assert fn.await_count == 2
    mock_sleep.assert_awaited_once()


async def test_exhausts_retries_and_raises_last_exception() -> None:
    """Should raise the last exception after exhausting all retries."""
    fn = AsyncMock(
        side_effect=[ValueError("fail1"), ValueError("fail2"), ValueError("fail3"), ValueError("fail4")]
    )

    with (
        patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(ValueError, match="fail4"),
    ):
        await with_retry(
            fn,
            RetryConfig(max_retries=3, base_delay=0.1),
            retryable_exceptions=(ValueError,),
        )

    # 1 initial + 3 retries = 4 attempts
    assert fn.await_count == 4


async def test_non_retryable_exception_propagates_immediately() -> None:
    """Non-retryable exceptions should propagate without any retry."""
    fn = AsyncMock(side_effect=TypeError("not retryable"))

    with (
        patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        pytest.raises(TypeError, match="not retryable"),
    ):
        await with_retry(
            fn,
            RetryConfig(max_retries=3),
            retryable_exceptions=(ValueError,),
        )

    fn.assert_awaited_once()
    mock_sleep.assert_not_awaited()


async def test_backoff_delays_increase_exponentially() -> None:
    """Backoff delays should increase exponentially (base_delay * 2^attempt) plus jitter."""
    fn = AsyncMock(
        side_effect=[ValueError("e1"), ValueError("e2"), ValueError("e3"), "ok"]
    )
    config = RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0)

    with (
        patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("amelia.core.retry.random.uniform", return_value=0.0),
    ):
        result = await with_retry(fn, config, retryable_exceptions=(ValueError,))

    assert result == "ok"
    assert mock_sleep.await_count == 3

    delays = [call.args[0] for call in mock_sleep.await_args_list]
    # With jitter=0: delays should be 1.0, 2.0, 4.0
    assert delays == [1.0, 2.0, 4.0]


async def test_max_delay_caps_backoff() -> None:
    """Delay should never exceed max_delay."""
    fn = AsyncMock(
        side_effect=[ValueError("e1"), ValueError("e2"), ValueError("e3"), "ok"]
    )
    config = RetryConfig(max_retries=3, base_delay=10.0, max_delay=15.0)

    with (
        patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("amelia.core.retry.random.uniform", return_value=0.0),
    ):
        result = await with_retry(fn, config, retryable_exceptions=(ValueError,))

    assert result == "ok"
    delays = [call.args[0] for call in mock_sleep.await_args_list]
    # base_delay * 2^0 = 10, base_delay * 2^1 = 20 -> capped to 15, same for 2^2
    assert delays == [10.0, 15.0, 15.0]


async def test_max_delay_caps_backoff_including_jitter() -> None:
    """Jitter should not push the final delay past max_delay."""
    fn = AsyncMock(side_effect=[ValueError("e1"), "ok"])
    config = RetryConfig(max_retries=2, base_delay=10.0, max_delay=22.0)

    with (
        patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("amelia.core.retry.random.uniform", return_value=5.0),
    ):
        result = await with_retry(fn, config, retryable_exceptions=(ValueError,))

    assert result == "ok"
    delays = [call.args[0] for call in mock_sleep.await_args_list]
    # base_delay * 2^0 = 10, jitter = 5 → 15, capped at 22 → 15 (under cap)
    assert delays == [15.0]


async def test_default_config_used_when_none() -> None:
    """Should use default RetryConfig when None is passed."""
    fn = AsyncMock(return_value="default")

    result = await with_retry(fn, config=None)

    assert result == "default"
    fn.assert_awaited_once()
