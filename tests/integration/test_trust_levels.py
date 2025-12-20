# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for trust level variations.

These tests verify that different trust levels affect checkpoint behavior
through the should_checkpoint function used by the orchestrator.
"""

from collections.abc import Callable

import pytest

from amelia.core.orchestrator import should_checkpoint
from amelia.core.state import (
    ExecutionBatch,
    PlanStep,
)
from amelia.core.types import Profile, TrustLevel


def _create_batch(risk_summary: str) -> ExecutionBatch:
    """Create an ExecutionBatch with the specified risk level.

    Args:
        risk_summary: The risk level for the batch (low, medium, or high).

    Returns:
        ExecutionBatch configured with the specified risk level.
    """
    return ExecutionBatch(
        batch_number=1,
        steps=(
            PlanStep(
                id="step-1",
                description=f"{risk_summary.capitalize()} risk step",
                action_type="command",
                command="echo test",
                risk_level=risk_summary,
            ),
        ),
        risk_summary=risk_summary,
        description=f"{risk_summary.capitalize()} risk batch",
    )


@pytest.mark.parametrize(
    "trust_level,enabled,risk,expected",
    [
        # PARANOID always checkpoints when enabled
        (TrustLevel.PARANOID, True, "low", True),
        (TrustLevel.PARANOID, True, "medium", True),
        (TrustLevel.PARANOID, True, "high", True),
        # STANDARD always checkpoints when enabled
        (TrustLevel.STANDARD, True, "low", True),
        (TrustLevel.STANDARD, True, "medium", True),
        (TrustLevel.STANDARD, True, "high", True),
        # AUTONOMOUS only checkpoints high risk when enabled
        (TrustLevel.AUTONOMOUS, True, "low", False),
        (TrustLevel.AUTONOMOUS, True, "medium", False),
        (TrustLevel.AUTONOMOUS, True, "high", True),
        # Disabled checkpoints never pause
        (TrustLevel.PARANOID, False, "high", False),
        (TrustLevel.AUTONOMOUS, False, "high", False),
    ],
    ids=[
        "paranoid_enabled_low",
        "paranoid_enabled_medium",
        "paranoid_enabled_high",
        "standard_enabled_low",
        "standard_enabled_medium",
        "standard_enabled_high",
        "autonomous_enabled_low",
        "autonomous_enabled_medium",
        "autonomous_enabled_high",
        "paranoid_disabled_high",
        "autonomous_disabled_high",
    ],
)
def test_should_checkpoint(
    trust_level: TrustLevel,
    enabled: bool,
    risk: str,
    expected: bool,
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Test should_checkpoint behavior across trust levels, checkpoint settings, and risk levels.

    Args:
        trust_level: The trust level to test (PARANOID, STANDARD, or AUTONOMOUS).
        enabled: Whether batch checkpoints are enabled.
        risk: The risk level of the batch (low, medium, or high).
        expected: The expected result of should_checkpoint.
        mock_profile_factory: Fixture to create a Profile instance.
    """
    profile = mock_profile_factory(
        trust_level=trust_level,
        batch_checkpoint_enabled=enabled,
    )
    batch = _create_batch(risk)

    assert should_checkpoint(batch, profile) is expected


def test_multiple_batches_mixed_risks_autonomous(
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """AUTONOMOUS mode with mixed risks should only checkpoint high-risk batches.

    This test validates that when multiple batches are evaluated sequentially,
    the checkpoint behavior remains consistent based on risk level.
    """
    profile = mock_profile_factory(
        trust_level=TrustLevel.AUTONOMOUS,
        batch_checkpoint_enabled=True,
    )

    # Create batches with different risk levels
    low_batch = ExecutionBatch(
        batch_number=1,
        steps=(
            PlanStep(
                id="step-1",
                description="Low risk",
                action_type="command",
                command="echo",
                risk_level="low",
            ),
        ),
        risk_summary="low",
        description="Low risk batch",
    )
    high_batch = ExecutionBatch(
        batch_number=2,
        steps=(
            PlanStep(
                id="step-2",
                description="High risk",
                action_type="command",
                command="rm",
                risk_level="high",
            ),
        ),
        risk_summary="high",
        description="High risk batch",
    )
    medium_batch = ExecutionBatch(
        batch_number=3,
        steps=(
            PlanStep(
                id="step-3",
                description="Medium risk",
                action_type="command",
                command="npm",
                risk_level="medium",
            ),
        ),
        risk_summary="medium",
        description="Medium risk batch",
    )

    # Only high risk should checkpoint
    assert should_checkpoint(low_batch, profile) is False
    assert should_checkpoint(high_batch, profile) is True
    assert should_checkpoint(medium_batch, profile) is False
