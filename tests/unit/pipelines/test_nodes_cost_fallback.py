"""Tests for cost fallback in _save_token_usage()."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.pipelines.nodes import _save_token_usage


_SENTINEL = object()


def _make_driver(
    *,
    model: str = "claude-sonnet-4-5-20251101",
    usage_model: object = _SENTINEL,
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cost_usd: float | None = None,
    duration_ms: int = 100,
    num_turns: int = 1,
) -> MagicMock:
    """Create a mock driver with a get_usage() method returning the given fields.

    Args:
        model: The driver.model attribute (fallback when usage.model is falsy).
        usage_model: The driver_usage.model value. Defaults to ``model`` when
            not explicitly provided; pass ``None`` to simulate a driver that
            doesn't report its model in usage.
    """
    usage = MagicMock()
    usage.model = model if usage_model is _SENTINEL else usage_model
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_tokens = cache_read_tokens
    usage.cache_creation_tokens = cache_creation_tokens
    usage.cost_usd = cost_usd
    usage.duration_ms = duration_ms
    usage.num_turns = num_turns

    driver = MagicMock()
    driver.get_usage.return_value = usage
    driver.model = model
    return driver


@pytest.fixture
def workflow_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def repository() -> AsyncMock:
    repo = AsyncMock()
    repo.save_token_usage = AsyncMock()
    return repo


async def test_calls_calculate_token_cost_when_cost_usd_is_none(
    workflow_id: uuid.UUID,
    repository: AsyncMock,
) -> None:
    """When driver_usage.cost_usd is None, _save_token_usage should call calculate_token_cost."""
    driver = _make_driver(cost_usd=None, input_tokens=1000, output_tokens=500)

    with patch(
        "amelia.pipelines.nodes.calculate_token_cost",
        new_callable=AsyncMock,
        return_value=0.042,
    ) as mock_calc:
        await _save_token_usage(driver, workflow_id, "developer", repository)

    mock_calc.assert_called_once_with(
        model="claude-sonnet-4-5-20251101",
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )
    saved = repository.save_token_usage.call_args[0][0]
    assert saved.cost_usd == 0.042


async def test_calls_calculate_token_cost_when_cost_usd_is_zero(
    workflow_id: uuid.UUID,
    repository: AsyncMock,
) -> None:
    """When driver_usage.cost_usd is 0, _save_token_usage should call calculate_token_cost."""
    driver = _make_driver(cost_usd=0.0, input_tokens=2000, output_tokens=800)

    with patch(
        "amelia.pipelines.nodes.calculate_token_cost",
        new_callable=AsyncMock,
        return_value=0.1,
    ) as mock_calc:
        await _save_token_usage(driver, workflow_id, "reviewer", repository)

    mock_calc.assert_called_once_with(
        model="claude-sonnet-4-5-20251101",
        input_tokens=2000,
        output_tokens=800,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )
    saved = repository.save_token_usage.call_args[0][0]
    assert saved.cost_usd == 0.1


async def test_uses_driver_cost_when_provided(
    workflow_id: uuid.UUID,
    repository: AsyncMock,
) -> None:
    """When driver_usage.cost_usd is nonzero, _save_token_usage should NOT call calculate_token_cost."""
    driver = _make_driver(cost_usd=0.55)

    with patch(
        "amelia.pipelines.nodes.calculate_token_cost",
        new_callable=AsyncMock,
    ) as mock_calc:
        await _save_token_usage(driver, workflow_id, "developer", repository)

    mock_calc.assert_not_called()
    saved = repository.save_token_usage.call_args[0][0]
    assert saved.cost_usd == 0.55


async def test_falls_back_to_driver_model_when_usage_model_is_none(
    workflow_id: uuid.UUID,
    repository: AsyncMock,
) -> None:
    """When driver_usage.model is None, the fallback should use driver.model."""
    driver = _make_driver(
        model="claude-opus-4-20250514",
        usage_model=None,
        cost_usd=None,
        input_tokens=500,
        output_tokens=200,
    )

    with patch(
        "amelia.pipelines.nodes.calculate_token_cost",
        new_callable=AsyncMock,
        return_value=0.03,
    ) as mock_calc:
        await _save_token_usage(driver, workflow_id, "developer", repository)

    mock_calc.assert_called_once_with(
        model="claude-opus-4-20250514",
        input_tokens=500,
        output_tokens=200,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )
    saved = repository.save_token_usage.call_args[0][0]
    assert saved.model == "claude-opus-4-20250514"


async def test_forwards_cache_tokens_to_calculate_token_cost(
    workflow_id: uuid.UUID,
    repository: AsyncMock,
) -> None:
    """Nonzero cache tokens should be forwarded to calculate_token_cost."""
    driver = _make_driver(
        cost_usd=None,
        input_tokens=3000,
        output_tokens=1000,
        cache_read_tokens=800,
        cache_creation_tokens=200,
    )

    with patch(
        "amelia.pipelines.nodes.calculate_token_cost",
        new_callable=AsyncMock,
        return_value=0.065,
    ) as mock_calc:
        await _save_token_usage(driver, workflow_id, "reviewer", repository)

    mock_calc.assert_called_once_with(
        model="claude-sonnet-4-5-20251101",
        input_tokens=3000,
        output_tokens=1000,
        cache_read_tokens=800,
        cache_creation_tokens=200,
    )
    saved = repository.save_token_usage.call_args[0][0]
    assert saved.cost_usd == 0.065
    assert saved.cache_read_tokens == 800
    assert saved.cache_creation_tokens == 200
