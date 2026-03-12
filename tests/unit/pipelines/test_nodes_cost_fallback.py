"""Tests for cost fallback in _save_token_usage()."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.pipelines.nodes import _save_token_usage


def _make_driver(
    *,
    model: str = "claude-sonnet-4-5-20251101",
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cost_usd: float | None = None,
    duration_ms: int = 100,
    num_turns: int = 1,
) -> MagicMock:
    """Create a mock driver with a get_usage() method returning the given fields."""
    usage = MagicMock()
    usage.model = model
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
