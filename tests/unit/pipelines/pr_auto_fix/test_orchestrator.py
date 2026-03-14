"""Tests for PR auto-fix orchestrator config and event types."""

import pytest
from pydantic import ValidationError

from amelia.core.types import PRAutoFixConfig
from amelia.server.models.events import EventType


class TestPRAutoFixConfigCooldown:
    """Tests for cooldown configuration fields on PRAutoFixConfig."""

    def test_default_post_push_cooldown(self) -> None:
        config = PRAutoFixConfig()
        assert config.post_push_cooldown_seconds == 300

    def test_default_max_cooldown(self) -> None:
        config = PRAutoFixConfig()
        assert config.max_cooldown_seconds == 900

    def test_post_push_exceeds_max_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="post_push_cooldown_seconds"):
            PRAutoFixConfig(
                post_push_cooldown_seconds=600,
                max_cooldown_seconds=300,
            )

    def test_post_push_less_than_max_succeeds(self) -> None:
        config = PRAutoFixConfig(
            post_push_cooldown_seconds=60,
            max_cooldown_seconds=120,
        )
        assert config.post_push_cooldown_seconds == 60
        assert config.max_cooldown_seconds == 120

    def test_both_zero_succeeds(self) -> None:
        config = PRAutoFixConfig(
            post_push_cooldown_seconds=0,
            max_cooldown_seconds=0,
        )
        assert config.post_push_cooldown_seconds == 0
        assert config.max_cooldown_seconds == 0


class TestPRFixEventTypes:
    """Tests for new PR fix orchestration event types."""

    @pytest.mark.parametrize(
        ("member", "value"),
        [
            ("PR_FIX_QUEUED", "pr_fix_queued"),
            ("PR_FIX_DIVERGED", "pr_fix_diverged"),
            ("PR_FIX_COOLDOWN_STARTED", "pr_fix_cooldown_started"),
            ("PR_FIX_COOLDOWN_RESET", "pr_fix_cooldown_reset"),
            ("PR_FIX_RETRIES_EXHAUSTED", "pr_fix_retries_exhausted"),
        ],
    )
    def test_event_type_exists_with_correct_value(
        self, member: str, value: str
    ) -> None:
        event = getattr(EventType, member)
        assert event == value
        assert isinstance(event, EventType)
