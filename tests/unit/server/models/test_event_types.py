# tests/unit/server/models/test_event_types.py
from amelia.server.models.events import TRACE_TYPES, EventType


class TestPlanEventTypes:
    def test_plan_validated_exists(self) -> None:
        assert EventType.PLAN_VALIDATED == "plan_validated"

    def test_plan_validation_failed_exists(self) -> None:
        assert EventType.PLAN_VALIDATION_FAILED == "plan_validation_failed"

    def test_plan_validated_is_not_trace(self) -> None:
        """Plan validation events are workflow-scoped, not trace broadcast."""
        assert EventType.PLAN_VALIDATED not in TRACE_TYPES

    def test_plan_validation_failed_is_not_trace(self) -> None:
        assert EventType.PLAN_VALIDATION_FAILED not in TRACE_TYPES
