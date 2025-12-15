# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for should_checkpoint helper function in orchestrator."""

from collections.abc import Callable

import pytest

from amelia.core.orchestrator import should_checkpoint
from amelia.core.state import ExecutionBatch, PlanStep
from amelia.core.types import Profile, TrustLevel


class TestShouldCheckpoint:
    """Tests for should_checkpoint function."""

    @pytest.fixture
    def low_risk_batch(self) -> ExecutionBatch:
        """Create a low-risk batch for testing."""
        step = PlanStep(
            id="step-1",
            description="Run tests",
            action_type="command",
            command="pytest",
            risk_level="low",
        )
        return ExecutionBatch(
            batch_number=1,
            steps=(step,),
            risk_summary="low",
            description="Low risk operations",
        )

    @pytest.fixture
    def medium_risk_batch(self) -> ExecutionBatch:
        """Create a medium-risk batch for testing."""
        step = PlanStep(
            id="step-2",
            description="Update config",
            action_type="code",
            file_path="config.py",
            risk_level="medium",
        )
        return ExecutionBatch(
            batch_number=2,
            steps=(step,),
            risk_summary="medium",
            description="Medium risk operations",
        )

    @pytest.fixture
    def high_risk_batch(self) -> ExecutionBatch:
        """Create a high-risk batch for testing."""
        step = PlanStep(
            id="step-3",
            description="Deploy to production",
            action_type="command",
            command="kubectl apply -f prod.yaml",
            risk_level="high",
        )
        return ExecutionBatch(
            batch_number=3,
            steps=(step,),
            risk_summary="high",
            description="High risk operations",
        )

    def test_paranoid_always_checkpoints_low_risk(
        self,
        low_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test PARANOID trust level always checkpoints, even for low-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.PARANOID,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(low_risk_batch, profile)

        # Assert
        assert result is True

    def test_paranoid_always_checkpoints_medium_risk(
        self,
        medium_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test PARANOID trust level always checkpoints for medium-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.PARANOID,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(medium_risk_batch, profile)

        # Assert
        assert result is True

    def test_paranoid_always_checkpoints_high_risk(
        self,
        high_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test PARANOID trust level always checkpoints for high-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.PARANOID,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(high_risk_batch, profile)

        # Assert
        assert result is True

    def test_standard_always_checkpoints_low_risk(
        self,
        low_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test STANDARD trust level always checkpoints, even for low-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.STANDARD,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(low_risk_batch, profile)

        # Assert
        assert result is True

    def test_standard_always_checkpoints_medium_risk(
        self,
        medium_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test STANDARD trust level always checkpoints for medium-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.STANDARD,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(medium_risk_batch, profile)

        # Assert
        assert result is True

    def test_standard_always_checkpoints_high_risk(
        self,
        high_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test STANDARD trust level always checkpoints for high-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.STANDARD,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(high_risk_batch, profile)

        # Assert
        assert result is True

    def test_autonomous_does_not_checkpoint_low_risk(
        self,
        low_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test AUTONOMOUS trust level does NOT checkpoint for low-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.AUTONOMOUS,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(low_risk_batch, profile)

        # Assert
        assert result is False

    def test_autonomous_does_not_checkpoint_medium_risk(
        self,
        medium_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test AUTONOMOUS trust level does NOT checkpoint for medium-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.AUTONOMOUS,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(medium_risk_batch, profile)

        # Assert
        assert result is False

    def test_autonomous_checkpoints_high_risk(
        self,
        high_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test AUTONOMOUS trust level checkpoints only for high-risk batches."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.AUTONOMOUS,
            batch_checkpoint_enabled=True,
        )

        # Act
        result = should_checkpoint(high_risk_batch, profile)

        # Assert
        assert result is True

    def test_checkpoint_disabled_never_checkpoints_low_risk(
        self,
        low_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test that batch_checkpoint_enabled=False prevents checkpoint for low-risk."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.PARANOID,
            batch_checkpoint_enabled=False,
        )

        # Act
        result = should_checkpoint(low_risk_batch, profile)

        # Assert
        assert result is False

    def test_checkpoint_disabled_never_checkpoints_medium_risk(
        self,
        medium_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test that batch_checkpoint_enabled=False prevents checkpoint for medium-risk."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.STANDARD,
            batch_checkpoint_enabled=False,
        )

        # Act
        result = should_checkpoint(medium_risk_batch, profile)

        # Assert
        assert result is False

    def test_checkpoint_disabled_never_checkpoints_high_risk(
        self,
        high_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test that batch_checkpoint_enabled=False prevents checkpoint even for high-risk."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.AUTONOMOUS,
            batch_checkpoint_enabled=False,
        )

        # Act
        result = should_checkpoint(high_risk_batch, profile)

        # Assert
        assert result is False

    def test_checkpoint_disabled_overrides_paranoid(
        self,
        high_risk_batch: ExecutionBatch,
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test that batch_checkpoint_enabled=False takes precedence over PARANOID trust level."""
        # Arrange
        profile = mock_profile_factory(
            trust_level=TrustLevel.PARANOID,
            batch_checkpoint_enabled=False,
        )

        # Act
        result = should_checkpoint(high_risk_batch, profile)

        # Assert
        assert result is False
