# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for should_checkpoint helper function in orchestrator."""

from collections.abc import Callable

import pytest

from amelia.core.orchestrator import should_checkpoint
from amelia.core.state import ExecutionBatch, PlanStep
from amelia.core.types import Profile, TrustLevel


@pytest.fixture
def make_batch() -> Callable[[str], ExecutionBatch]:
    """Factory to create batches with specified risk level."""

    def _make(risk_level: str) -> ExecutionBatch:
        step = PlanStep(
            id=f"step-{risk_level}",
            description=f"Test {risk_level} step",
            action_type="command",
            command="echo test",
            risk_level=risk_level,
        )
        return ExecutionBatch(
            batch_number=1,
            steps=(step,),
            risk_summary=risk_level,
            description=f"{risk_level.title()} risk operations",
        )

    return _make


class TestShouldCheckpoint:
    """Tests for should_checkpoint function."""

    @pytest.mark.parametrize(
        "trust_level,risk_level,checkpoint_enabled,expected",
        [
            # PARANOID: always checkpoints when enabled
            (TrustLevel.PARANOID, "low", True, True),
            (TrustLevel.PARANOID, "medium", True, True),
            (TrustLevel.PARANOID, "high", True, True),
            # STANDARD: always checkpoints when enabled
            (TrustLevel.STANDARD, "low", True, True),
            (TrustLevel.STANDARD, "medium", True, True),
            (TrustLevel.STANDARD, "high", True, True),
            # AUTONOMOUS: only high-risk checkpoints when enabled
            (TrustLevel.AUTONOMOUS, "low", True, False),
            (TrustLevel.AUTONOMOUS, "medium", True, False),
            (TrustLevel.AUTONOMOUS, "high", True, True),
            # Disabled: never checkpoints regardless of trust/risk
            (TrustLevel.PARANOID, "low", False, False),
            (TrustLevel.STANDARD, "medium", False, False),
            (TrustLevel.AUTONOMOUS, "high", False, False),
            (TrustLevel.PARANOID, "high", False, False),
        ],
        ids=[
            "paranoid_low_enabled",
            "paranoid_medium_enabled",
            "paranoid_high_enabled",
            "standard_low_enabled",
            "standard_medium_enabled",
            "standard_high_enabled",
            "autonomous_low_enabled",
            "autonomous_medium_enabled",
            "autonomous_high_enabled",
            "paranoid_low_disabled",
            "standard_medium_disabled",
            "autonomous_high_disabled",
            "disabled_overrides_paranoid_high",
        ],
    )
    def test_checkpoint_decision_matrix(
        self,
        trust_level: TrustLevel,
        risk_level: str,
        checkpoint_enabled: bool,
        expected: bool,
        make_batch: Callable[[str], ExecutionBatch],
        mock_profile_factory: Callable[..., Profile],
    ) -> None:
        """Test checkpoint decisions across all trust/risk/enabled combinations."""
        batch = make_batch(risk_level)
        profile = mock_profile_factory(
            trust_level=trust_level,
            batch_checkpoint_enabled=checkpoint_enabled,
        )

        result = should_checkpoint(batch, profile)

        assert result is expected
