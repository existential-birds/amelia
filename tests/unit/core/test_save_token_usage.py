"""Tests for orchestrator _save_token_usage using DriverUsage."""
from unittest.mock import AsyncMock, MagicMock

from amelia.drivers.base import DriverUsage
from amelia.server.models.tokens import TokenUsage


class TestSaveTokenUsageWithDriverUsage:
    """Tests for _save_token_usage() using get_usage() method."""

    async def test_saves_usage_from_driver_get_usage(self) -> None:
        """_save_token_usage should call driver.get_usage() and save to repository."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=1500,
            output_tokens=500,
            cache_read_tokens=1000,
            cache_creation_tokens=200,
            cost_usd=0.025,
            duration_ms=5000,
            num_turns=3,
            model="test-model",
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        mock_driver.get_usage.assert_called_once()
        mock_repository.save_token_usage.assert_called_once()

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert isinstance(saved_usage, TokenUsage)
        assert saved_usage.workflow_id == "wf-123"
        assert saved_usage.agent == "developer"
        assert saved_usage.model == "test-model"
        assert saved_usage.input_tokens == 1500
        assert saved_usage.output_tokens == 500
        assert saved_usage.cache_read_tokens == 1000
        assert saved_usage.cache_creation_tokens == 200
        assert saved_usage.cost_usd == 0.025
        assert saved_usage.duration_ms == 5000
        assert saved_usage.num_turns == 3

    async def test_noop_when_get_usage_returns_none(self) -> None:
        """_save_token_usage should not save when get_usage() returns None."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = None

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        mock_repository.save_token_usage.assert_not_called()

    async def test_noop_when_repository_is_none(self) -> None:
        """_save_token_usage should not attempt save when repository is None."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = DriverUsage(input_tokens=100)

        # Should not raise
        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=None,
        )

        # No assertion on get_usage - we short-circuit before calling it

    async def test_defaults_none_fields_to_zero(self) -> None:
        """_save_token_usage should use 0 for None fields in DriverUsage."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.model = "fallback-model"
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            # All other fields None
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="architect",
            repository=mock_repository,
        )

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert saved_usage.input_tokens == 100
        assert saved_usage.output_tokens == 50
        assert saved_usage.cache_read_tokens == 0  # Default
        assert saved_usage.cache_creation_tokens == 0  # Default
        assert saved_usage.cost_usd == 0.0  # Default
        assert saved_usage.duration_ms == 0  # Default
        assert saved_usage.num_turns == 1  # Default

    async def test_uses_driver_model_when_usage_model_is_none(self) -> None:
        """_save_token_usage should fall back to driver.model when DriverUsage.model is None."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.model = "driver-model"
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            model=None,  # No model in usage
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert saved_usage.model == "driver-model"

    async def test_uses_unknown_when_no_model_available(self) -> None:
        """_save_token_usage should use 'unknown' when model unavailable everywhere."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock(spec=["get_usage"])  # No model attribute
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            model=None,
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="reviewer",
            repository=mock_repository,
        )

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert saved_usage.model == "unknown"

    async def test_handles_driver_without_get_usage(self) -> None:
        """_save_token_usage should handle drivers without get_usage gracefully."""
        from amelia.core.orchestrator import _save_token_usage

        # Driver without get_usage (uses spec to exclude it)
        mock_driver = MagicMock(spec=["generate", "execute_agentic"])

        mock_repository = AsyncMock()

        # Should not raise
        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        mock_repository.save_token_usage.assert_not_called()

    async def test_handles_repository_error_gracefully(self) -> None:
        """_save_token_usage should log but not raise on repository errors."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
        )

        mock_repository = AsyncMock()
        mock_repository.save_token_usage.side_effect = Exception("DB error")

        # Should not raise
        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )
